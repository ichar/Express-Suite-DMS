"""
E-mail related classes:

    'Charset' -- national character set convertor class

    'MailMessage' -- representation of the RFC-822 e-mail message class

    'MailFilter' -- filter class which can be matched against messages

    'MailServerBase' -- abstract base class for all incoming and outgoing mail servers

    'MailServer' -- client class for communication with POP-3 servers

    'MailSender' -- client class for communication with SMTP servers

$Id: Mail.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 15/03/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from zLOG import LOG, TRACE, INFO, ERROR

import re
from copy import copy
from re import escape, compile, sub
from string import join, capitalize
from types import StringType, UnicodeType, TupleType, ListType, DictType
from sys import exc_info
import threading

import base64
import email.base64MIME, email.quopriMIME
from email import __version__ as _email_version
from email.Charset import Charset as _Charset, BASE64, QP, ALIASES, CODEC_MAP
from email.Encoders import _bencode
from email.Generator import _is8bitstring
from email.Header import Header as _Header, ecre as _header_ecre, \
     USASCII as _charset_USASCII, UTF8 as _charset_UTF8
#from email.Header import decode_header
from email.Message import Message as _Message
from email.Parser import Parser
from email.Utils import parseaddr, getaddresses, formatdate, make_msgid, specialsre, escapesre
from email.base64MIME import body_encode as base64_encode
from email.quopriMIME import body_encode as quopri_encode
from poplib import POP3, error_proto
from smtplib import SMTP as _SMTP, SMTPSenderRefused, SMTPRecipientsRefused, SMTPException
from urllib import splittype, splithost

try:
    import hmac
except ImportError:
    hmac = None

from Acquisition import Implicit, aq_base, aq_parent, aq_get
from AccessControl import ClassSecurityInfo
from AccessControl import Permissions as ZopePermissions
from AccessControl.Role import RoleManager
from AccessControl.SecurityManagement import getSecurityManager
from BTrees.OOBTree import OOBTree

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName, _checkPermission

from Products.MailHost.MailHost import MailHost

import Config
from Config import Permissions
from ConflictResolution import ResolveConflict
from Exceptions import SimpleError, Unauthorized
from MemberDataTool import MemberData
from SimpleObjects import Persistent, InstanceBase

from Utils import InitializeClass, joinpath, getLanguageInfo, isCharsetKnown, recode_string, \
     isInstance, CheckAntiSpam

_default_charset = getLanguageInfo()[ 'mail_charset' ]
_meta_ctype_rec  = re.compile( '<meta\b[^>]+\bhttp-equiv="?Content-Type"?[^>]*>', re.I )

if hasattr( _SMTP, 'login' ):
    SMTP = _SMTP
else:
    class SMTP( _SMTP ):

        def login(self, user, password):
            """
               For Python 2.1 and lower compatibility.
        
               Log in on an SMTP server that requires authentication.

               The arguments are:
               - user:     The user name to authenticate with.
               - password: The password for the authentication.

               If there has been no previous EHLO or HELO command, this
               method tries ESMTP EHLO first.

               This method will return normally if the authentication was successful.

            """
            
            def encode_base64(s, eol=None):
                return "".join(base64.encodestring(s).split("\n"))
                
            def encode_cram_md5(challenge, user, password):
                challenge = base64.decodestring(challenge)
                response = user + " " + hmac.HMAC(password, challenge).hexdigest()
                return base64_encode(response, eol="")

            def encode_plain(user, password):
                return base64_encode("%s\0%s\0%s" % (user, user, password), eol="")


            AUTH_PLAIN = "PLAIN"
            AUTH_CRAM_MD5 = "CRAM-MD5"
            AUTH_LOGIN = "LOGIN"

            if self.helo_resp is None and self.ehlo_resp is None:
                if not (200 <= self.ehlo()[0] <= 299):
                    (code, resp) = self.helo()
                    if not (200 <= code <= 299):
                        raise SMTPHeloError(code, resp)

            if not self.has_extn("auth"):
                raise SMTPException("SMTP AUTH extension not supported by server.")

            # Authentication methods the server supports:
            authlist = self.esmtp_features["auth"]
            if authlist.startswith('='):
                authlist = authlist[1:]
            authlist = authlist.split()
            # List of authentication methods we support: from preferred to
            # less preferred methods. Except for the purpose of testing the weaker
            # ones, we prefer stronger methods like CRAM-MD5:
                           
            preferred_auths = [AUTH_CRAM_MD5, AUTH_PLAIN, AUTH_LOGIN]
            if hmac is None:
                preferred_auths.remove(AUTH_CRAM_MD5)
            
            # Determine the authentication method we'll use
            authmethod = None
            for method in preferred_auths:
                if method in authlist:
                    authmethod = method
                    break

            if authmethod == AUTH_CRAM_MD5:
                (code, resp) = self.docmd("AUTH", AUTH_CRAM_MD5)
                if code == 503:
                    # 503 == 'Error: already authenticated'
                    return (code, resp)
                (code, resp) = self.docmd(encode_cram_md5(resp, user, password))
            elif authmethod == AUTH_PLAIN:
                (code, resp) = self.docmd("AUTH",
                    AUTH_PLAIN + " " + encode_plain(user, password))
            elif authmethod == AUTH_LOGIN:
                (code, resp) = self.docmd("AUTH",
                    "%s %s" % (AUTH_LOGIN, encode_base64(user, eol="")))
                if code != 334:
                    raise SMTPException("Authorization failed.")
                (code, resp) = self.docmd(encode_base64(password, eol=""))
            elif authmethod == None:
                raise SMTPException("No suitable authentication method found.")
            if code not in [235, 503]:
                # 235 == 'Authentication successful'
                # 503 == 'Error: already authenticated'
                raise SMTPException("Authorization failed.")
            return (code, resp)


class Charset( _Charset ):
    """
        National character set convertor.

        Attributes:

            'input_charset' -- name of the source encoding

            'input_changed' --  a flag used by the mail message parser

            'input_codec' -- name of the codec from input charset to Unicode

            'output_charset' -- name of the target encoding

            'output_codec' -- name of the codec from Unicode to output charset
    """

    input_changed = None

    def __init__( self, input_charset=_default_charset, output_charset=None ):
        """
            Initializes new 'Charset' instance.

            Arguments:

                'input_charset' -- optional source encoding name,
                        by default is set to the charset corresponding
                        to 'Config.DefaultLanguage' value

                'output_charset' -- optional target encoding name,
                        default value is selected from 'CHARSETS' mapping
                        (see 'email.Charset' module) using 'input_charset'
                        value as the lookup key
        """
        _Charset.__init__( self, input_charset )

        if output_charset is not None:
            output_charset = output_charset.lower()
            master_charset = ALIASES.get( output_charset, output_charset )
            self.output_charset = output_charset
            self.output_codec   = CODEC_MAP.get( master_charset, self.input_codec )

    def change_input_charset( self, charset ):
        """
            Changes source encoding and input codec.

            Arguments:

                'charset' -- new source encoding name
        """
        master_charset = ALIASES.get( charset, charset )
        if master_charset != self.input_charset:
            self.input_changed = 1
            self.input_charset = charset
            self.input_codec   = CODEC_MAP.get( master_charset, self.input_codec )

    def convert( self, text ):
        """
            Converts a string from source to target encoding.

            Arguments:

                'text' -- the string to be converted

            Result:

                String in the target encoding.
        """
        if self.input_codec != self.output_codec:
            return unicode( text, self.input_codec, 'ignore' ).encode( self.output_codec, 'ignore' )
        else:
            return text

    def body_encode( self, text, convert=1 ):
        """
            Encodes a string using body encoding for the input charset.

            Available body encodings are *base64*, *quoted-printable*,
            *7bit* and *8bit*.  The actual encoding used is selected
            from 'CHARSETS' mapping (see 'email.Charset' module) depending
            on the source encoding.

            Arguments:

                'text' -- the string to be encoded

                'convert' -- boolean flag, indicating that the string
                             must be first converted to the target encoding;
                             true by default

            Result:

                Body-encoded string.
        """
        if convert:
            text = self.convert(text)
        # 7bit/8bit encodings return the string unchanged (module conversions)
        if self.body_encoding is BASE64:
            return base64_encode(text)
        elif self.body_encoding is QP:
            return quopri_encode(text)
        else:
            return text

    def clone( self ):
        """
            Returns a copy of this object.

            Result:

                New 'Charset' object with 'input_changed' attribute
                reset to 'None' and all other attribute values copied.
        """
        new = copy( self )
        try: del new.input_changed
        except AttributeError: pass
        return new


class Header( _Header ):
    """
        Internet mail message header.
    """

    def __init__( self, s=None, charset=None,
                  maxlinelen=None, header_name=None,
                  continuation_ws=' ', errors='ignore' ):
        if _email_version >= '2.5':
            _Header.__init__( self, s, charset, maxlinelen, header_name, continuation_ws, errors )
        else:
            _Header.__init__( self, s, charset, maxlinelen, header_name, continuation_ws )

    def append( self, s, charset=None, errors='ignore' ):
        """
            Appends a string to the MIME header.

            This method is entirely copied from 'email.Header' module,
            with error handling for character encoding set to 'ignore'.
        """
        if charset is None:
            charset = self._charset
        elif not isinstance(charset, _Charset):
            charset = _Charset(charset)
        if charset <> '8bit':
            if isinstance(s, StringType):
                incodec = charset.input_codec or 'us-ascii'
                ustr = unicode(s, incodec)
                outcodec = charset.output_codec or 'us-ascii'
                ustr.encode(outcodec, errors)
            elif isinstance(s, UnicodeType):
                for charset in _charset_USASCII, charset, _charset_UTF8:
                    try:
                        outcodec = charset.output_codec or 'us-ascii'
                        s = s.encode(outcodec, errors)
                        break
                    except UnicodeError:
                        pass
                else:
                    assert False, 'utf-8 conversion failed'
        self._chunks.append((s, charset))


class MailMessage( _Message ):
    """
        Internet mail message class (RFC 822, 2822).

        See 'email' package description for additional information.

        The most important difference of this implementation is advanced
        support for automatic text convertion between character sets used
        in electronic mail system and in Web portal documents.

        Another significant concept is an introduction of the *message
        body* which contains the main text of the message.  This is the
        message object itself for a simple message or the first part
        of the multipart message.
    """

    # default attribute values
    _in_parser    = None
    _hint_charset = None

    def __init__( self, ctype=None, multipart=None, source=None, charset=None, to_mail=None ):
        """
            Initializes new mail message.

            If the message is created as multipart, additional part for
            the main body is created with 'ctype' type and is attached
            to the multipart object.

            Positional arguments:

                'ctype' -- optional MIME content type for the body
                        of the message; may be changed later

            Keyword arguments:

                'multipart' -- if evaluated to truth, the message is created
                        as multipart with subtype set to the value of this
                        argument ('mixed' is used if it's not a string)

                'source' -- RFC 822 text (with headers and body) that
                        is parsed into the body of this message

                'charset' -- 'Charset' object used for character encoding
                        conversion
        """
        _Message.__init__( self )
        self._hint_charset = charset

        if multipart:
            multipart = type(multipart) is StringType and multipart.lower() or 'mixed'
            body = self.__class__( ctype, charset=charset )
            self.set_type( 'multipart/' + multipart )
            self.attach( body )
            self.epilogue = '' # ensure newline at EOF
        else:
            body = self
            if ctype:
                body.set_type( ctype )
        
        if source:
            # TODO: set initial charset to '8bit' when converting from mail
            body.from_text( source.lstrip(), charset, to_mail=to_mail )

    def __setitem__( self, name, value ):
        """
            Adds a field to the message header.

            If the value contains 8bit characters, new 'Header' object
            is created with the same charset parameters as given in the
            constructor, thus enabling automatic charset converions for
            the field contents.

            Arguments:

                'name' -- the name of the field

                'value' -- contents of the field
        """
        name = '-'.join( map( capitalize, name.strip().split('-') ) )

        if type(value) is TupleType and type(value[1]) is DictType:
            value, params = value
        else:
            params = None

        if type(value) is TupleType:
            # (name, address) pair
            value = formataddr( value, self._hint_charset )

        elif _is8bitstring( value ):
            value = Header( value, self._hint_charset )

        if not params or type(value) is not StringType:
            # TODO params are ignored for now
            self._headers.append( (name, value) )

        elif _is8bitstring( value ):
            value = Header( value, self._hint_charset )
            for k, v in params.items():
                # TODO must treat pairs as _formatparam does
                value.append( '; ' )
                value.append( k + '=' + v )
            self._headers.append( (name, value) )

        else:
            self.add_header( name, value, **params )

        # this is a workaround for charset problems
        # with badly formed cyrillic message headers
        if self._in_parser and self._hint_charset and not self._charset \
                           and name.lower() == 'content-type':
            charset = self.get_content_charset()
            if isCharsetKnown( charset ):
                self._hint_charset.change_input_charset( charset )

    def set_header( self, name, value, **params ):
        """
            Sets a header field value and parameters.

            This method basically works by removing existing headers
            with the same name and the calling '__setitem__' method.

            Positional arguments:

                'name' -- the name of the field

                'value' -- contents of the field

            Keyword arguments:

                '**params' -- additional field parameters

            Result:

                Value of the new header.
        """
        self.remove_header( name )
        self[ name ] = params and (value, params) or value
        return self._headers[-1][1]

    def remove_header( self, *names ):
        """
            Deletes all occurrences of the specified headers.

            Arguments:

                '*names' -- the list of the header names
        """
        for name in names:
            del self[ name.strip() ]

    def get( self, name, default=None, decode=None, maxlen=None ):
        """
            Returns a header field value.

            Positional arguments:

                'name' -- the name of the field

                'default' -- default value to return if the requested
                        field does not exist in the header; 'None' if
                        not given

            Keyword arguments:

                'decode' -- if true, the value is decoded and converted
                        to the target character set, otherwise (default)
                        the value is returned as-is

                'maxlen' -- currently not implemented

            Result:

                Value of the named field or default value.

            Note:

                See 'email' package for additional information.
        """
        header = _Message.get( self, name, default )

        # XXX a hack for _get_params_preserve - calls us with default=[]
        # always decode the field cause it does not support Header objects
        decode = decode or type(default) is ListType

        if header is default or not decode:
            return header

        # TODO implement maxlen
        return recode_header( header, self._hint_charset )

    def get_all( self, name, default=MissingValue, decode=None ):
        """
            Returns a list of all values for the named field, in case
            there are multiple fields with the same name in the message.

            Positional arguments:

                'name' -- the name of the field

                'default' -- default value to return if the requested
                        field does not exist in the header; empty list
                        if not given

            Keyword arguments:

                'decode' -- if true, the values are decoded and converted
                        to the target character set, otherwise (default)
                        the values are returned as-is

            Result:

                A list of values of the named field or default value.

            Note:

                See 'email' package for additional information.
        """
        headers = _Message.get_all( self, name, default )

        if headers is default or not decode:
            if headers is MissingValue:
                return []
            return headers

        charset = self._hint_charset
        return [ recode_header( header, charset ) for header in headers ]

    def get_param( self, param, default=None, header='content-type', unquote=1, decode=None ):
        """
            Returns the parameter value of the header field.

            Positional arguments:

                'param' -- the name of the parameter

                'default' -- default value to return if the requested
                        parameter does not exist in the field; 'None'
                        if not given

                'header' -- the name of the field to search the parameter
                        in; by default 'Content-Type' field is searched

            Keyword arguments:

                'unquote' -- if true (default) the value is unquoted

                'decode' -- if true, the value is decoded and converted
                        to the target character set, otherwise (default)
                        the value is returned as-is

            Result:

                Value of the named parameter or default value.

            Note:

                See 'email' package for additional information.
        """
        param = _Message.get_param( self, param, default, header, unquote )

        if type(param) is TupleType:
            return '' # TODO

        #if param is default or not decode:
        #    return param

        # XXX why is this commented out???
        #return recode_header( param, self._hint_charset )

        # XXX _get_params_preserve does not support Header objects
        return param

    def get_filename( self, default=None, decode=None ):
        """
            Returns the filename associated with the payload if present.

            The filename is determined by first looking for parameter
            'filename' in the 'Content-Disposition' header and then
            for parameter 'name' in the 'Content-Type' header.

            Positional arguments:

                'default' -- default value to return if the filename
                        canot be determined; 'None' if not given

            Keyword arguments:

                'decode' -- if true, the filename is decoded and converted
                        to the target character set, otherwise (default)
                        the value is returned as-is

            Result:

                Filename string or default value.
        """
        return self.get_param( 'filename', None, 'content-disposition', decode=decode ) \
            or self.get_param( 'name', default, 'content-type', decode=decode )

    def set_payload( self, payload, charset=None ):
        """
            Sets message payload (message contents) to the given data.

            For 'text/html' content type, '<meta http-equiv="Content-Type">'
            tag in the HTML header is added or modified so that its 'charset'
            parameter corresponds to the 'output_charset' value of the
            associated 'Charset' object.

            Non-textual contents is encoded using 'base64' algorithm with
            'Content-transfer-encoding' header set accordingly.

            Arguments:

                'payload' -- message data

                'charset' -- optional character set of the data for text messages

            Note:

                See 'email' package for additional information.
        """
        if self.is_text():
            if not ( charset or self.get_content_charset() ) and _is8bitstring( payload ):
                charset = self._hint_charset

            #if isinstance( charset, StringType ):
            #    hint = self._hint_charset
            #    charset = Charset( charset, hint and hint.output_charset or None )

            if charset:
                # actual transfer encoding is determined by body_encoding of the Charset object
                self.remove_header( 'content-transfer-encoding' )

            if self.get_subtype() == 'html':
                # fix text/html with "meta http-equiv=Content-Type"
                if charset:
                    meta = '<meta http-equiv="Content-Type" content="text/html; charset=%s">' % charset.output_charset
                else:
                    meta = ''
                payload = _meta_ctype_rec.sub( meta, payload, 1 )
                
        elif not self._in_parser:
            self.set_header( 'content-transfer-encoding', 'base64' )
            payload = _bencode( payload )

        _Message.set_payload( self, payload, charset )

    def get_payload( self, index=None, decode=None ):
        """
            Returns the payload (contents) of the message.

            Positional arguments:

                'index' -- for multipart message this is a number
                        (starting from 0) of the part to return (optional)

            Keyword arguments:

                'decode' -- if true, the textual contents is decoded and
                        converted to the target character set, otherwise
                        (default) the contents is returned as-is

            Result:

                Message contents as a string, or list of parts if the message
                is multipart and 'index' is not given.

            Note:

                See 'email' package for additional information.
        """
        if self.is_multipart():
            return _Message.get_payload( self, index, 0 )

        text = _Message.get_payload( self, index, decode=decode )

        if decode:
            if text is None:
                text = ''
            elif self.is_text() and text:
                charset = self.get_content_charset()
                if charset:
                    text = recode_string( text, self._hint_charset, enc_from=charset )

        return text

    def attach( self, payload, inline=None, filename=None, cid=None, location=None ):
        """
            Adds an attachment to the current payload.

            Note:

                See 'email' package for additional information.
        """
        if payload._hint_charset is None:
            payload._hint_charset = self._hint_charset

        if not ( inline is None and filename is None ):
            inline = inline and 'inline' or 'attachment'

        if filename:
            charset = self._hint_charset
            if charset:
                filename = charset.header_encode( filename )
            payload.set_header( 'content-disposition', inline, filename=filename )

        elif inline:
            payload.set_header( 'content-disposition', inline )

        if cid:
            payload.set_header( 'content-id', '<%s>' % cid )

        if location:
            payload.set_header( 'content-location', location )

        _Message.attach( self, payload )

    def get_body( self ):
        """
            Return the main body of the message.

            The body object contains the main text of the message.
            This may be the message object itself for a simple message
            or the first part of the multipart message.

            Result:

                'MailMessage' object.
        """
        if not self.is_multipart():
            return self
        return self.get_payload(0)

    def is_text( self ):
        """
            Checks whether message content type is text.

            Result:

                Truth if the content type is 'text/*'.
        """
        return self.get_main_type() == 'text'

    def from_text( self, text, charset=None, to_mail=None ):
        """
            Parses RFC 822 text into the message.

            Positional arguments:

                'text' -- source RFC 822 text (with headers and body)

            Keyword arguments:

                'charset' -- 'Charset' object used for character encoding
                        conversion

            Result:

                This object.
        """
        self._in_parser = 1
        if charset is not None:
            self._hint_charset = charset

        Parser( self._factory ).parsestr( text )

        for part in self.walk():
            self._in_parser = 0

        if 'content-type' not in self:
            self.set_type( 'text/plain' )
            self.set_charset( self._hint_charset )

        if not self.get_charset() and to_mail:
            self.set_charset( self._hint_charset )

        return self

    def _factory( self ):
        # class factory hacked for the MIME parser.
        if self._in_parser == 1:
            new = self
        else:
            new = self.__class__()
            new._in_parser = 1

        charset = self._hint_charset
        if charset and charset.input_changed:
            charset = charset.clone()
        new._hint_charset = charset

        self._in_parser += 1

        return new


class MailFilter( Persistent ):
    """
        Filter that can be applied on incoming mail messages
    """
    _class_version = 1.0

    def _initstate( self, mode ):
        """ Initialize attributes
        """
        if not Persistent._initstate( self, mode ):
            return 0

        if getattr( self, 'cond', None ) is None:
            self.cond = []

        return 1

    def reset( self ):
        del self.cond[:]
        self._p_changed = 1

    def get( self, id ):
        for c in self.cond:
            if c[0] == id:
                return c[4]
        return None

    def add( self, item, *vals, **args ):
        id  = args.get( 'id',   None )
        op  = args.get( 'op',   None )
        nm  = args.get( 'name', None )
        lst = []
        lst.extend( vals )
        if args.has_key('list'):
                lst.extend( args['list'] )
        self.cond.append( ( id, item, op, nm, lst ) )
        self._p_changed = 1

    def match( self, msg ):
        r = 1
        for c in self.cond:
            if c[1] == 'header':
                r = _substr( msg, c[4], c[3] )
            elif c[1] == 'sender':
                r = _email( msg, c[4], 'from', 'reply-to', 'sender', 'return-path', 'x-envelope-from' )
            elif c[1] == 'recipient':
                r = _email( msg, c[4], 'to', 'cc', 'bcc', 'resent-to', 'resent-cc', 'x-envelope-to' )
            if c[2] == '!':
                r = not r
            if not r:
                break
        return r

InitializeClass( MailFilter )


class MailServerBase( InstanceBase, RoleManager ):
    """
        Abstract base class for the mail services.
    """
    _class_version = 1.01

    meta_type = None

    security = ClassSecurityInfo()

    security.declareProtected( ZopePermissions.change_configuration, 'manage_changeProperties' )
    security.declareProtected( ZopePermissions.change_configuration, 'manage_editProperties' )

    manage_options = InstanceBase.manage_options + \
                     RoleManager.manage_options

    _properties = InstanceBase._properties + (
            {'id':'host', 'type':'string', 'mode':'w'},
            {'id':'port', 'type':'int', 'mode':'w'},
        )

    index_html = None

    # default attribute values
    protocol = None
    default_host = ''
    default_port = None
    min_interval = None
    _v_conn = None

    def __init__( self, id, title='', host=None, port=None ):
        """
            Initialize new instance.

            Arguments:

                'id' -- identifier of the new object

                'title' -- optional title of the new object, empty string by default

                'host' -- address of the host where the server is running

                'port' -- optional port number on which the server is listening for connections
        """
        InstanceBase.__init__( self, id, title )
        self.host = (host is not None) and str( host ) or self.default_host
        self.port = (port is not None) and int( port ) or self.default_port

    def _p_resolveConflict( self, oldState, savedState, newState ):
        """
            Try to resolve conflict between container's objects
        """
        return ResolveConflict('MailServerBase', oldState, savedState, newState, 'catalog', \
                                mode=1 \
                                )

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not InstanceBase._initstate( self, mode ):
            return 0

        if mode: LOG('MailServerBase initstate', INFO, 'autoupdate class version: %s' % self._class_version)

        if getattr( self, 'catalog', None ) is None:
            self.catalog = {}

        if type(self.catalog) is OOBTree:
            catalog = {}
            for x in self.catalog.keys():
                catalog[x] = self.catalog.get(x)
            self.catalog = catalog
            self._p_changed = 1

            LOG('MailServerBase initstate', INFO, 'keys: %s' % len(self.catalog.keys()))

        return 1

    def __del__( self ):
        # cleanup resources; rather useless
        if self._p_changed is None:
            return # it's too late to do something
        self.close()

    security.declarePrivate( 'open' )
    def open( self ):
        """
            Opens connection to the server.
        """
        pass

    security.declarePrivate( 'close' )
    def close( self ):
        """
            Closes server connection.
        """
        self._v_conn = None

    #security.declarePrivate( 'address' )
    def address( self, host=None, port=None ):
        """
            Returns or changes hostname and port of the server.

            Arguments:

                'host' -- address of the host where the server
                        is running

                'port' -- optional port number on which the server
                        is listening for connections

            Result:

                Server address string formatted as '"host:port"'.
        """
        if host is not None:
            parts = str( host ).split( ':', 1 )
            self.host = parts[0]
            if len(parts) > 1:
                self.port = int( parts[1] )

        if port is not None:
            self.port = int( port )

        if not self.host or self.port == self.default_port:
            return self.host

        return join( (self.host, str(self.port)), ':' )

    security.declarePrivate( 'getInputCharset' )
    def getInputCharset( self, lang=None ):
        """
            Returns 'Charset' instance that can be used to decode
            incoming mail for this server.

            Arguments:

                'lang' -- optional language code used to determine target
                        character set; if not given, default language
                        of the portal is used

            Result:

                'Charset' object.
        """
        langinfo = getLanguageInfo( lang or self )
        return Charset( langinfo['mail_charset'], langinfo['python_charset'] )

    security.declarePrivate( 'getOutputCharset' )
    def getOutputCharset( self, lang=None ):
        """
            Returns 'Charset' instance that can be used to encode
            outgoing mail for this server.

            Arguments:

                'lang' -- optional language code used to determine source
                        character set; if not given, default language
                        of the portal is used

            Result:

                'Charset' object.
        """
        langinfo = getLanguageInfo( lang or self )
        return Charset( langinfo['python_charset'], langinfo['mail_charset'] )

    security.declarePrivate( 'createMessage' )
    def createMessage( self, *args, **kw ):
        """
            Creates a new mail message instance.

            Arguments:

                '*args', '**kw' -- arguments for the 'MailMessage'
                        constructor

            Result:

                'MailMessage' object.
        """
        return MailMessage( *args, **kw )

    security.declarePrivate( 'register_account' )
    def register_account( self, object, item, force=0 ):
        item = item and item.strip().lower()
        if not item:
            raise # TODO
        return self.replace_account( None, item, object, force )

    security.declarePrivate( 'unregister_account' )
    def unregister_account( self, item, object, force=0 ):
        return self.replace_account( item, None, object, force )

    security.declarePrivate( 'replace_account' )
    def replace_account( self, item, dest, object, force=0 ):
        item = item and item.strip().lower()
        dest = dest and dest.strip().lower()

        try:
            uid = object.getUid()
        except AttributeError:
            uid = joinpath( object.getPhysicalPath() )

        catalog = self.catalog
        old = catalog.get(item)
        changed = 0

        if old is not None:
            if uid == old:
                if dest == item:
                    return None
                del catalog[item]
                changed = 1
            elif force and dest != item:
                del catalog[item]
                changed = 1

        if dest:
            new = catalog.get(dest)
            if new is not None:
                if uid == new:
                    return None
                elif not force:
                    raise KeyError, "duplicate account '%s'" % dest
            catalog[dest] = uid
            changed = 1
        else:
            uid = None

        if changed:
            self.catalog = catalog
            self._p_changed = 1

        return uid

    security.declarePrivate( 'has_account' )
    def has_account( self, item ):
        item = item and item.strip().lower()
        if not item:
            return None
        return self.catalog.get(item, 0)

    security.declareProtected( ZopePermissions.change_configuration, 'listAccounts' )
    def listAccounts( self ):
        # returns a list of all registered accounts
        return list(self.catalog.keys())

    security.declareProtected( ZopePermissions.change_configuration, 'manage_deleteAccounts' )
    def manage_deleteAccounts( self, items, REQUEST=None ):
        """
            Removes accounts.
        """
        catalog = self.catalog
        changed = 0
        # Delete registered accounts
        for item in items:
            try:
                del catalog[item]
                changed = 1
            except KeyError: pass

        if changed:
            self.catalog = catalog
            self._p_changed = 1

        if REQUEST is not None:
            return REQUEST.RESPONSE.redirect( self.absolute_url() + '/manage_MailServer', status=303 )

    def _instance_onClone( self, source, item ):
        # unregister all accounts
        try: self.catalog.clear()
        except: self.catalog = {}
        self._p_changed = 1

InitializeClass( MailServerBase )


class MailServer( MailServerBase ):
    """
        POP3 mail service class.
    """
    _class_version = 1.0

    meta_type = 'Mail Server'

    security = ClassSecurityInfo()

    protocol = 'pop'
    default_port = 110

    # default attribute values
    _v_folder = _v_uids = _v_indx = _v_seen = None

    def open( self, login, password ):
        """
            Opens connection to the server.

            Arguments:

                'login' -- login name string

                'password' -- password string
        """
        if self._v_conn is not None:
            self.close()

        try:
            self._v_conn = POP3( self.host, self.port )
        except:
            LOG( 'MailServer.open', ERROR, '[%s] connect failed' % self.address(), error=exc_info() )
            raise

        try:
            self._v_conn.user( str(login) )
            self._v_conn.pass_( str(password) or '""' )
        except:
            LOG( 'MailServer.open', ERROR, '[%s] unable to login as "%s"' % ( self.address(), login ), error=exc_info() )
            raise

        self._v_login = login

    def close( self ):
        """
            Closes server connection.
        """
        self._v_login = self._v_folder = None
        self._v_uids  = self._v_indx = self._v_seen = None

        if self._v_conn is not None:
            try:
                self._v_conn.quit()
            except:
                LOG( 'MailServer.close', ERROR, '[%s] disconnect error' % self.address(), error=exc_info() )

        MailServerBase.close( self )

    security.declarePrivate( 'folder' )
    def folder( self, name=Config.MailInboxName, seen=None ):
        """
            Selects named folder (always 'INBOX' for POP3) for work.

            Positional arguments:

                'name' -- folder name

            Keyword arguments:

                'seen' -- optional mapping containing UIDs of messages
                        already seen by the client
        """
        if name != Config.MailInboxName:
            raise SimpleError, 'invalid folder name "%s"' % name

        if self._v_conn is None:
            self.open()

        if self._v_folder != name:
            self._v_folder = name
            self._v_uids = self._v_indx = self._v_seen = None

        if seen is not None:
            self._v_seen = seen

    security.declarePrivate( 'fetch' )
    def fetch( self, all=0, seen=None, mark=None ):
        """
            Fetches messages from the current folder.

            Keyword arguments:

                'all' -- boolean flag indicating that all messages on
                        the server should be fetched; default is to fetch
                        only messages with their UIDs not in 'seen' mapping

                'seen' -- mapping containing UIDs of messages seen
                        by the client

                'mark' -- boolean flag, if true (default) then UIDs of
                        fetched messages are inserted into 'seen' mapping

            Result:

                A list of 'MailMessage' objects.
        """
        conn = self._v_conn
        indx = self._v_indx
        msgs = []

        if seen is None:
            seen = self._v_seen
            if seen is None:
                all  = 1
                mark = 0

        elif mark is None:
            mark = 1

        if indx is None:
            try:
                indx = self._getUids()
            except:
                LOG( 'MailServer.fetch', ERROR, '[%s@%s] error getting message index' % ( self._v_login, self.address() ), error=exc_info() )
                raise

        #LOG( 'MailServer.fetch', TRACE, 'server has %d message(s)' % len(indx) )

        for i, uid in indx:
            if not all and seen.has_key( uid ):
                continue

            #LOG( 'MailServer.fetch', TRACE, 'retrieving message %d uid=%s' % (i, uid) )

            try:
                res, lines, size = conn.retr( i )
            except:
                LOG( 'MailServer.fetch', ERROR, '[%s@%s] cannot retrieve message %d uid=%s' % ( self._v_login, self.address(), i, uid ), \
                    error=exc_info() )
                continue

            try:
                msg = self.createMessage( source=join( lines, '\n') )
            except:
                LOG( 'MailServer.fetch', ERROR, '[%s@%s] cannot parse message %d uid=%s' % (self._v_login, self.address(), i, uid), \
                    error=exc_info() )
                continue

            msg.uid = uid
            msgs.append( msg )

            if mark:
                seen[ uid ] = 1

        return msgs

    security.declarePrivate( 'delete' )
    def delete( self, uid=None, old=0, all=0 ):
        """
            Deletes a message from the current folder.

            Positional arguments:

                'uid' -- UID of the message to delete

            Keyword arguments:

                'old' -- boolean flag indicating that messages already
                        seen should be deleted; overrides 'uid' argument

                'all' -- boolean flag indicating that all messages on
                        the server should be deleted; overrides both 'uid'
                        and 'old' arguments

            Result:

                Number of deleted messages.

            Note:

                In POP3 messages are not actually deleted until QUIT.
        """
        conn = self._v_conn
        uids = self._v_uids
        indx = self._v_indx
        seen = self._v_seen
        count = 0

        if all:
            num, size = conn.stat()

            for i in range( 1, num + 1 ):
                try:
                    conn.dele( i )
                    count += 1
                except error_proto:
                    pass

            if indx:
                del indx[:]
            uids and uids.clear()
            seen and seen.clear()

            return count

        if indx is None:
            indx = self._getUids()
            uids = self._v_uids

        if old:
            if seen is None:
                raise # TODO
            lst = seen.keys()
        else:
            # TODO allow multiple uids in the arguments
            lst = [ uid ]

        for uid in lst:
            if not uids.has_key( uid ):
                continue

            try:
                conn.dele( uids[ uid ][0] )
                count += 1
            except error_proto:
                pass

            indx.remove( uids[ uid ] )
            del uids[ uid ]

        if old:
            seen.clear()

        elif seen:
            for uid in lst:
                try: del seen[ uid ]
                except KeyError: pass

        return count

    def _getUids( self ):
        """
            Returns UIDs of messages in the current folder.

            If 'seen' mapping was given when selecting folder,
            clears it from UIDs not on the server anymore.

            Result:

                List of (<message number>, <UID string>) pairs.
        """
        uids = self._v_uids = {}
        indx = self._v_indx = []
        seen = self._v_seen

        try:
            res, lines, size = self._v_conn.uidl()
        except error_proto:
            return indx

        for line in lines:
            i, uid = line.strip().split()
            indx.append( (int(i), uid) )
            uids[ uid ] = indx[ -1 ]

        if seen:
            for uid in seen.keys():
                if not uids.has_key( uid ):
                    del seen[ uid ]

        return indx

    security.declareProtected( Permissions.UseMailServerServices, 'createMessage' )
    def createMessage( self, *args, **kw ):
        """
            Creates a new mail message instance with character set
            conversion from e-mail to portal encoding.

            Arguments:

                '*args', '**kw' -- arguments for the 'MailMessage'
                        constructor

            Result:

                'MailMessage' object.
        """
        if not kw.has_key('charset'):
            kw['charset'] = self.getInputCharset()
        return MailServerBase.createMessage( self, *args, **kw )

InitializeClass( MailServer )


class MailSender( MailServerBase, MailHost ):
    """
        SMTP mail service class.

        Surpasses 'MailHost' product, which it is based on and retains
        compatibility with.
    """
    _class_version = 1.0

    meta_type = 'Mail Sender'

    security = ClassSecurityInfo()

    protocol = 'smtp'
    default_port = 25
    
    _login = None
    _password = None

    def open( self ):
        """
            Opens connection to the server.
        """
        if self._v_conn is not None:
            return

        if not self.address():
            return

        self._v_conn = SMTP( self.host, self.port )
        
        login = self.login()
        password = self.password()
        if login is not None:
            try:
                self._v_conn.login( login, password )
            except SMTPException:
                LOG( 'MailSMTP.open', ERROR, '[%s] unable to login as "%s"' % ( self.address(), login ), error=exc_info() )
                raise
    
    def close( self ):
        """
            Closes server connection.
        """
        if self._v_conn is not None:
            self._v_conn.quit()

        MailServerBase.close( self )

    security.declareProtected( ZopePermissions.change_configuration, 'login' )
    def login( self ):
        """
            Returns login to SMTP server required 
            authentication.
        """
        return self._login
    
    security.declareProtected( ZopePermissions.change_configuration, 'password' )
    def password( self ):
        """
            Returns password to SMTP server required 
            authentication.
        """
        return self._password
    
    security.declareProtected( ZopePermissions.change_configuration, 'setCredentials' )
    def setCredentials( self, login=MissingValue, password=MissingValue ):
        """
            Set login and password to SMTP server required 
            authentication.
     
            Arguments:
             
                'login' -- login to SMTP server (email address)
                'password' -- password to SMTP server (email address).
            
        """
        if login is not MissingValue:
            self._login = login
        if password is not MissingValue:
            self._password = password
    
    security.declarePublic( 'sendTemplate' )
    def sendTemplate( self, template, mto=None, mfrom=None, subject=None, \
                      from_member=None, raise_exc=MissingValue, IsAntiSpam=None, \
                      namespace=None, lang=None, REQUEST=None, **kw ):
        """
            Creates a new message from a DTML template and sends it through
            the SMTP server.

            This method renders DTML document or method and sends result
            by SMTP as an e-mail message.  The template to send can be
            specified as the object itself, or by its identifier, which
            is used as a key for lookup in the 'Mail' skin of the portal.
            In both cases, the current user must have *Reply to item* access
            right on the template object, otherwise an exception is raised.

            The template receives current acquisition context as the client
            object, 'namespace' argument or request as DTML namespace, with
            additional keyword arguments put on top of the namespace, along
            with the language code as 'lang' variable.

            Positional arguments:

                'template' -- document template object or identifier string

                'mto', 'mfrom', 'subject' -- see 'send()' method description

            Keyword arguments:

                'from_member' -- see 'send()' method description

                'raise_exc' -- if true, ignore delivery errors; DTML errors
                        are raised nonetheless

                'namespace' -- mapping object that represents DTML namespace

                'lang' -- language code passed to the template; if omitted,
                        default language of the portal is used

                'REQUEST' -- optional Zope request object; if 'namespace'
                        argument is omitted, request is used instead

                '**kw' -- additional variables to pass to the template

            Result:

                See 'send()' method description.

            Exceptions:

                'Unauthorized' -- the current user has insufficient
                        rights to send the template

            Note:

                This method is declared public so that it can be used
                by objects on the external sites.
        """
        context = aq_parent( self )

        if callable( template ):
            id = template.getId()

        else:
            id = template
            skins = getToolByName( context, 'portal_skins' )
            try:
                template = getattr( skins.getSkinByName('Mail'), id )
            except ( AttributeError, KeyError ):
                raise KeyError, id
            # XXX move this to skins tool
            template = aq_base( template ).__of__( context )

        if not _checkPermission( CMFCorePermissions.ReplyToItem, template ):
            raise Unauthorized, id

        # XXX must use language from recipients' settings
        lang = lang or getToolByName( self, 'msg' ).get_default_language()

        if type(mto) is StringType:
            mto = (mto,)
        elif isinstance( mto, MemberData ):
            mto = list(mto.getMemberName())

        membership = getToolByName( self, 'portal_membership', None )
        if not membership:
            return None

        count = 0
        check_list_to = []

        for x in mto:
            if x in check_list_to or not x:
                continue

            if x.find('@') > -1:
                member_email = x
                IsAntiSpam = 0
            else:
                member_email = membership.getMemberById( x ).getMemberEmail()
                if IsAntiSpam is None:
                    IsAntiSpam = CheckAntiSpam( self, x )

            mail_text = template( context, namespace or REQUEST, lang=lang, IsAntiSpam=IsAntiSpam, **kw )

            msg = self.createMessage( source=mail_text )
            if self.send( msg, mto=(member_email,), mfrom=mfrom, subject=subject, from_member=from_member, raise_exc=raise_exc ):
                check_list_to.append( x )
                count += 1

        #if count:
        #    LOG('Mail.sendTemplate', INFO, "message was sent: mfrom %s, mto %s, subject %s" % (mfrom, mto, subject) )
        return count

    def send( self, msg, mto=None, mfrom=None, subject=None, encode=None, from_member=None, \
                    IsAntiSpam=None, IsReturnReceiptTo=None, IsConfirmReadingTo=None, \
                    object_url=None, raise_exc=MissingValue ):
        """
            Sends a message through the SMTP server.

            The message to send can be either an object or a string.
            In the latter case, the string is directly passed to the
            'MailHost' product along with other arguments for compatibility.
            The connection to the server is opened automatically.

            Both sender and recipients may be specified either as e-mail
            addresses or portal user names.

            If sender address is not given, the message in sent on behalf
            of either portal administrative address or the current user
            depending on 'from_member' argument.

            If recipients list is omitted, the list of addresses is
            extracted from all of 'To', 'CC', 'BCC', 'Resent-To' and
            'Resent-CC' fields of the message.

            Additionally 'Date', 'Message-Id' and 'X-Mailer' fields in
            the header are set before delivery, and 'BCC' field is removed
            for security.

            Positional arguments:

                'msg' -- 'MailMessage' object or a string

                'mto' -- optional list of recipients

                'mfrom' -- optional address of the message originator

                'subject' -- optional message subject; overrides
                        one in the message

                'encode' -- only for compatibility with 'MailHost' product

            Keyword arguments:

                'from_member' -- boolean value, determines whether
                        administrative address (by default) or address
                        of the current user (if value is true) is used
                        as the message source if 'mfrom' argument is omitted

                'raise_exc' -- if true, delivery errors are ignored

            Result:

                Number of successful recipient addresses.
        """
        count = 0
        if not self.address():
            LOG( 'MailSender.send', TRACE, 'SMTP address is not defined')
            return 0

        try:
            if not isinstance( msg, MailMessage ):
                count = MailHost.send( self, msg, mto, mfrom, subject, encode )
                LOG( 'MailSender.send', TRACE, 'sent mail messages: count [%s], from %s to %s ' % ( count, mfrom, mto ))
                self.close()
                return count

            if subject is not None:
                msg.set_header( 'subject', subject )
            else:
                subject = ''

            if 'date' not in msg:
                msg.set_header( 'date', formatdate( None, 1 ) )
            if 'message-id' not in msg:
                msg.set_header( 'message-id', make_msgid() )
            if 'x-mailer' not in msg:
                msg.set_header( 'x-mailer', Config.MailerName % self._class_version )

            membership = getToolByName( self, 'portal_membership', None )
            properties = getToolByName( self, 'portal_properties', None )
            if membership is None or properties is None:
                return 0

            member = mname = None

            if mfrom is None:
                if from_member and not membership.isAnonymousUser():
                    member = membership.getAuthenticatedMember()
                elif 'from' in msg:
                    mfrom = parseaddr( msg.get( 'from', decode=1 ) )[1]
                    if not mfrom:
                        mfrom = properties.getProperty( 'email_from_address' )
                else:
                    mname = properties.getProperty( 'email_from_name' )
                    if IsAntiSpam != 0:
                        try: mfrom = properties.getProperty( 'email_antispam' )
                        except: pass
                    if not mfrom:
                        mfrom = properties.getProperty( 'email_from_address' )
                    else:
                        mname = None
            else:
                if type(mfrom) is StringType:
                    if mfrom.find('@') < 0:
                        member = membership.getMemberById( mfrom )
                elif isinstance( mfrom, MemberData ):
                    member = mfrom

            if member is not None:
                mname = member.getMemberName()
                mfrom = member.getMemberEmail()

            if not mfrom:
                mfrom = getSecurityManager().getUser().getUserName()

            if 'from' not in msg:
                msg.set_header( 'from', (mname, mfrom) )

            list_to = None

            if mto is None:
                mdict = {}
                for header in ( 'to', 'cc', 'bcc', 'resent-to', 'resent-cc' ):
                    for mname, email in getaddresses( msg.get_all( header ) ):
                        if email:
                            mdict[ email ] = header
                mto = mdict.keys()
            elif 'to' in msg:
                list_to = []

            if 'bcc' in msg:
                msg.remove_header( 'bcc' )

            if IsReturnReceiptTo:
                msg.set_header( 'Disposition-Notification-To', mfrom )
                msg.set_header( 'Return-Receipt-To', mfrom )

            if IsConfirmReadingTo:
                msg.set_header( 'Return-Receipt-To', mfrom )
                msg.set_header( 'Disposition-Notification-To', mfrom )
                msg.set_header( 'X-Confirm-Reading-To', mfrom )

            no_mail = membership.getGroupMembers('_NO_MAIL_') or []
            if mto and type(mto) is StringType:
                mto = [ mto ]
            check_list_to = []

            for item in mto:
                member = None
                if type(item) is StringType:
                    if item.find('@') < 0:
                        member = membership.getMemberById( item )
                elif isinstance( item, MemberData ):
                    member = item

                if member is not None:
                    mname = member.getMemberName()
                    email = member.getMemberEmail()
                else:
                    mname = None
                    email = str(item)

                if member is not None and member.getUserName() in no_mail:
                    continue

                if not email or email == '' or email == 'None' or email.find('@') < 1:
                    LOG( 'MailSender.send', ERROR, 'no e-mail address for user "%s", subject "%s", users: %s' % \
                       ( item, subject, `mto` ))
                    continue

                if email in check_list_to:
                    continue
                check_list_to.append( email )

                if list_to is None:
                    msg.set_header( 'to', (mname, email) )
                    count += self._send( mfrom, [email], msg )
                else:
                    list_to.append( email )

            if list_to:
                count = self._send( mfrom, list_to, msg )

            # TODO: find a way to disconnect only after request is processed
            self.close()

            if count:
                LOG('MailSender.send', INFO, 'mail address list: object [%s]\n>from %s to %s\n>total messages %s' % \
                   ( object_url or subject, mfrom, check_list_to, count ))
            else:
                LOG('MailSender.send', INFO, 'no mail')
        except:
            if raise_exc or raise_exc is MissingValue:
                raise
            else:
                LOG('MailSender.send', ERROR, '[%s] sending failed' % self.address(), error=exc_info())

        return count

    def _send( self, *args ):
        # send the message (overrides MailHost method)
        if self._v_conn is None:
            self.open()

        if len(args) == 2: # Zope 2.5
            mfrom, mto = args[0]['from'], args[0]['to']
        else:
            mfrom, mto = args[0:2]

        body = args[-1]
        if isinstance( body, MailMessage ):
            body = body.as_string()

        # TODO: set 8BITMIME from C-T-E
        #LOG( 'MailSender._send', TRACE, 'sending mail:\n%s => %s\n%s' % (mfrom, str(mto), body) )
        
        options = []
        count = len( mto )
        errors = None

        # TODO set 8bitmime only if necessary (from C-T-E)
        if self._v_conn.has_extn( '8bitmime' ):
            options.append( 'body=8bitmime' )

        try:
            errors = self._v_conn.sendmail( mfrom, mto, body, options )
        except SMTPSenderRefused, exc:
            LOG( 'MailSender._send', ERROR, '[%s] SMTP sender address <%s> refused' % ( self.address(), exc.sender ) )
            raise
        except SMTPRecipientsRefused, exc:
            errors = exc.recipients

        if errors:
            LOG( 'MailSender._send', ERROR, '[%s] SMTP errors during send:' % self.address() )
            for addr, error in errors.items():
                LOG( 'MailSender._send', ERROR, '- <%s> - %s %s' % ( addr, error[0], error[1] ) )
            count = count - len( errors )

        #self._v_conn.rset()

        return count

    security.declareProtected( Permissions.UseMailHostServices, 'createMessage' )
    def createMessage( self, *args, **kw ):
        """
            Creates a new mail message instance with character set
            conversion from portal to e-mail encoding.

            Arguments:

                '*args', '**kw' -- arguments for the 'MailMessage'
                        constructor

            Result:

                'MailMessage' object.
        """
        if not kw.has_key('charset'):
            kw['charset'] = self.getOutputCharset()
        kw['to_mail'] = 1
        return MailServerBase.createMessage( self, *args, **kw )

InitializeClass( MailSender )


def manage_addMailServer( self, id='MailServer', title='', host=None, port=None, REQUEST=None ):
    """
        Creates a new MailServer instance and adds it into the container
    """
    self._setObject( id, MailServer( id, title, host, port ) )

    if REQUEST is not None:
        REQUEST.RESPONSE.redirect( REQUEST.URL1 )

def manage_addMailSender( self, id='MailHost', title='', host=None, port=None, REQUEST=None ):
    """
        Creates a new MailSender instance and adds it into the container
    """
    self._setObject( id, MailSender( id, title, host, port ) )

    if REQUEST is not None:
        REQUEST.RESPONSE.redirect( REQUEST.URL1 )

def initialize( context ):

    context.registerClass(
        MailServer,
        permission	= Permissions.AddMailServerObjects,
        constructors	= ( manage_addMailServer, ),
    )

    context.registerClass(
        MailSender,
        permission	= Permissions.AddMailHostObjects,
        constructors	= ( manage_addMailSender, ),
    )

def formataddr( pair, charset=None ):
    """
        Formats name and e-mail address pair into string, properly
        encoding and converting characters if necessary.

        Arguments:

            'pair' -- tuple of strings (<real name>, <e-mail address>);
                    if name is empty, address is returned as-is

            'charset' -- optional 'Charset' object for character
                    set convertion

        Returns:

            String suitable for RFC 822 header.
    """
    name, address = pair
    name = name and name.strip()
    address = address and address.strip()

    if not name:
        return address

    if _is8bitstring( name ):
        header = Header( '"%s"' % name, charset )
        header.append( ' <%s>' % address, '8bit' )
        return header

    quotes = ''
    if specialsre.search( name ):
        quotes = '"'
    name = escapesre.sub( r'\\\g<0>', name )

    return '%s%s%s <%s>' % ( quotes, name, quotes, address )

def recode_header( header, charset=None ):
    # converts characters in the header
    if isInstance( header, _Header ):
        chunks = header._chunks
    else:
        chunks = decode_header( header )
    result = ''
    for value, enc in chunks:
        if isInstance( enc, _Charset ):
            enc = enc.input_charset
        result += recode_string( value, charset, enc_from=enc )
    return result

def _substr( msg, vals, *headers ):
    # substring match for MailFilter
    s = join( [ escape(s.strip()) for s in vals ], '|' )
    regex = compile( '(?:' + s + ')', re.I )

    for hdr in headers:
        for item in msg.get_all( hdr, decode=1 ):
            if regex.search( item ):
                return 1
    return 0

def _email( msg, vals, *headers ):
    # email match for MailFilter
    addrs = []

    for s in vals:
        u, h = map( escape, s.strip().split( '@', 1 ) )
        u = u.replace( r'\*', r'[^@]*' )
        h = h.replace( r'\*\.', r'[^@.]*\.' )
        h = h.replace( r'\*', r'(?:[^@]*(?:\.|\.*$))?' )
        addrs.append( u + '@' + h )

    regex = compile( '^(?:' + join( addrs, '|' ) + ')$', re.I )

    for hdr in headers:
        lst = msg.get_all( hdr, decode=1 )
        if not lst:
            continue
        for name, email in getaddresses( lst ):
            #if regex.match( email.strip().rstrip('.') ): # needs python 2.2
            if regex.match( email.strip() ):
                return 1
    return 0

# decode_header() from email package eats whitespace between
# encoded and non-encoded words. Thus we use this fixed version.

def decode_header( header ):
    # If no encoding, just return the header
    header = str(header)
    if not _header_ecre.search(header):
        return [(header, None)]
    decoded = []
    dec = ''
    for line in header.splitlines():
        # This line might not have an encoding in it
        if not _header_ecre.search(line):
            decoded.append((line, None))
            continue
        parts = _header_ecre.split(line)
        while parts:
            unenc = parts.pop(0)
            if not unenc.strip():
                unenc = ''
            if unenc:
                # Should we continue a long line?
                if decoded and decoded[-1][1] is None:
                    decoded[-1] = (decoded[-1][0] + unenc, None)
                else:
                    decoded.append((unenc, None))
            if parts:
                charset, encoding = [s.lower() for s in parts[0:2]]
                encoded = parts[2]
                dec = ''
                if encoding == 'q':
                    dec = email.quopriMIME.header_decode(encoded)
                elif encoding == 'b':
                    dec = email.base64MIME.decode(encoded)
                else:
                    dec = encoded

                if decoded and decoded[-1][1] == charset:
                    decoded[-1] = (decoded[-1][0] + dec, decoded[-1][1])
                else:
                    decoded.append((dec, charset))
            del parts[0:3]
    return decoded

def getContentId( object, extra=None ):
    """
        Returns string suitable for MIME 'Content-Id' header.
    """
    url = getToolByName( object, 'portal_url' )( canonical=True )
    host, path = splithost( splittype(url)[1] )
    cid = host.replace(':','_') + path.replace('/','_') + '.' + object.getUid()
    if extra:
        cid += '.%s' * extra
    return cid
