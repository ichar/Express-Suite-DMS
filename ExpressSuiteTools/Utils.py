"""
Utils functions
$Id: Utils.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 07/07/2009 ***

"""
__version__ = "$Revision: 1.0 $"[11:-2]

import sys, os, re
import base64, os.path, marshal, string

from cgi import escape
from email.Charset import ALIASES, CHARSETS
from posixpath import normpath, split as splitpath, splitext
from types import ClassType, InstanceType, MethodType, DictType, TupleType, ListType, UnicodeType, \
     StringType, IntType, FloatType, LongType, ComplexType, BooleanType, StringTypes
from random import randrange
from urllib import quote, unquote

from ZODB.POSException import ConflictError, ReadConflictError
from Globals import InitializeClass as _InitializeClass, get_request

from Acquisition import aq_get, aq_inner, aq_parent, aq_base
from AccessControl.SecurityManagement import get_ident, getSecurityManager, newSecurityManager, \
     noSecurityManager, _managers as SecurityManagers

from App.Common import package_home
from BTrees.IIBTree import union, intersection
from DateTime import DateTime
from time import strftime, localtime

from ExtensionClass import ExtensionClass #, ExtensionMethodType, PythonMethodType
from Interface.Implements import getImplementsOfInstances
from ZPublisher.HTTPRequest import record as _zpub_record

from OFS.CopySupport import _cb_decode
from OFS.Moniker import loadMoniker
from OFS.ObjectManager import checkValidId, BadRequestException
from OFS.Uninstalled import BrokenClass

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import _checkPermission, minimalpath, expandpath
from Products.CMFCore.utils import getToolByName
from Products.CMFCore.DirectoryView import registerMetaType, registerFileExtension
from Products.CMFCore.FSDTMLMethod import FSDTMLMethod
from Products.CMFCore.FSPythonScript import FSPythonScript
from Products.CMFCore.FSImage import FSImage
from Products.CMFDefault.Document import Document

import Config
from Config import AppClasses

from logging import getLogger
logger = getLogger()

pathdelim = '/'

BooleanTypes  = ( IntType is BooleanType ) and ( BooleanType, ) or ( BooleanType, IntType )
ClassTypes    = [ ClassType, ExtensionClass ]
MappingTypes  = ( DictType, _zpub_record )
MethodTypes   = [ MethodType ] #, ExtensionMethodType, PythonMethodType:, FSDTMLMethod, FSPythonScript
NumericTypes  = ( IntType, LongType, FloatType, ComplexType )
SequenceTypes = ( TupleType, ListType )


def AnonymousUserName( context ):
    anonymous_user = 'Anonymous User'
    msg = getToolByName( context, 'msg', None )
    return msg is not None and msg(anonymous_user) or anonymous_user

def check_request( context=None, REQUEST=None ):
    if REQUEST is not None:
        return REQUEST
    request = None
    if context is not None:
        request = aq_get( context, 'REQUEST', None )
    if request is None:
        request = get_request() or {}
    return request

def GetInstance( context ):
    """
        Returns current portal instance name
    """
    instance = ''
    try:
        instance = getToolByName( context, 'portal_properties', None ).instance_name()
        if not instance:
            instance = context.getPortalObject().getId()
    except:
        try:
            instance = aq_get( context, 'instance', None, 1 ) or ''
        except:
            pass
    return instance

def GetSessionValue( context, name, default=None, REQUEST=None, cookie=None ):
    """
        Get session value
    """
    if not name or name.lower().startswith('none'):
        return default
    if REQUEST is None:
        REQUEST = check_request( context, REQUEST )
    if Config.DefaultSession == 'cookie' or cookie:
        attr_name = '%s_%s' % ( GetInstance( context ) or 'default', name )
        try: x = REQUEST.get(attr_name) or REQUEST.cookies.get(attr_name) or default
        except: pass
        if x and type(default) != type(x):
            return eval( x )
        return x
    else:
        return REQUEST.SESSION.get(name) or default

def SetSessionValue( context, name, value, REQUEST=None, cookie=None ):
    """
        Set session value
    """
    if not name or name.lower().startswith('none'):
        return
    if REQUEST is None:
        REQUEST = check_request( context, REQUEST )
    if Config.DefaultSession == 'cookie' or cookie:
        attr_name = '%s_%s' % ( GetInstance( context ) or 'default', name )
        try: REQUEST.RESPONSE.setCookie(attr_name, value, path='/', expires='Wed, 19 Feb 2020 14:28:00 GMT')
        except: pass
    else:
        REQUEST.SESSION[name] = value

def ExpireSessionValue( context, name, REQUEST=None, cookie=None ):
    """
        Expire session value
    """
    if REQUEST is None:
        REQUEST = check_request( context, REQUEST )
    if Config.DefaultSession == 'cookie' or cookie:
        attr_name = '%s_%s' % ( GetInstance( context ) or 'default', name )
        try: REQUEST.RESPONSE.expireCookie(attr_name, path='/')
        except: pass
    else:
        REQUEST.SESSION[name] = None

def getLanguageInfo( context=None, default=MissingValue ):
    """
        Returns language information for the given language.

        The language information structure is looked up in the
        'Config.Languages' variable either by the given language code
        or by the default language of the portal if an object
        is passed as the first argument.

        Raises 'KeyError' if invalid language is specified and
        no default value given.

        Arguments:

            'context' -- language code, as indicated in the *Config* file,
                         or any object through which portal root can be acquired;
                         if not specified, 'Config.DefaultLanguage' is used

            'default' -- value to be returned if the requested language
                         is not valid

        Result:

            Dictionary as defined in the Config.
    """
    if context is None:
        lang = Config.DefaultLanguage
    elif aq_parent( context ) is not None:
        lang = getToolByName( context, 'msg' ).get_default_language()
    else:
        lang = str(context)

    try:
        return Config.Languages[ lang ]

    except KeyError:
        if default is MissingValue:
            raise
        return default

_default_charset = getLanguageInfo()['python_charset']

def isCharsetKnown( charset ):
    # checks whether the charset name is valid
    if not charset:
        return None
    charset = charset.lower()
    charset = ALIASES.get( charset, charset )
    return CHARSETS.has_key( charset ) and charset or None

def recode_string( text, charset=None, enc_from=None, enc_to=None, default=MissingValue ):
    """
        Recodes given string from one character set to another.

        Characters unsupported by the source or target encoding
        are removed from the result.  If neither encoding nor charset
        object is specified for input or output, character set
        corresponding to the 'Config.DefaultLanguage' value is used.

        If any of the encodings is not supported then all potentially
        unsafe characters are removed from the string (generally leaving
        only ASCII set in the result), unless default value is given,
        which is returned as the result.

        Arguments:

            'text' -- the string to be recoded

            'charset' -- optional 'Charset' object, used if encoding
                         arguments are omitted

            'enc_from' -- optional name of the source encoding;
                          if not specified, input encoding of the
                          'charset' object is used

            'enc_to' -- optional name of the target encoding;
                        if not specified, output encoding of the
                        'charset' object is used

            'default' -- optional default value that is returned
                         if any of the character sets is unknown

        Result:

            Recoded string or default value.
    """
    if charset:
        enc_from = enc_from or charset.input_charset
        enc_to = enc_to or charset.output_charset

    if enc_from == enc_to:
        return text

    enc_from = ( enc_from or _default_charset ).lower()
    enc_from = ALIASES.get( enc_from, enc_from )

    enc_to = ( enc_to or _default_charset ).lower()
    enc_to = ALIASES.get( enc_to, enc_to )

    try:
        text = unicode( text, enc_from, 'ignore' ).encode( enc_to, 'ignore' )

    except ( LookupError, UnicodeError ):
        if default is MissingValue:
            text = secureString( text )
        else:
            text = default

    return text


_safe_rec = re.compile( '[%s]' % re.escape( string.printable ) )

def secureString( text ):
    # removes potentially unsafe characters from the string
    return _safe_rec.sub( '', text )

# XXX move this to localizer
def translit_string( text, lang ):
    """
        Returns given string transliterated to the ASCII set.

        Uses mappings in 'Config.TransliterationMap'.

        Arguments:

            'text' -- the string to be transliterated

            'lang' -- language code of the source

        Result:

            Transliterated string.
    """
    if not text:
        return text

    charmap = Config.TransliterationMap.get( (lang,) )
    if not charmap:
        if type(text) is not UnicodeType:
            text = unicode( text, 'ascii', 'ignore' )
        return text.encode( 'ascii', 'ignore' )

    if type(text) is UnicodeType:
        text = text.encode( getLanguageInfo( lang )['python_charset'], 'ignore' )

    result = ''
    for c in text:
        result += charmap[c]

    return result

def check_unique_subject( title, description ):
    """
        Checks given string as valid title\description.
    """
    if not description:
        return 0
    title = translit_string( title.strip(), 'ru' ).lower()
    description = translit_string( description.strip(), 'ru' ).lower()
    symbols = '.,; \-\=\\\/\*\+\(\)\&\^\%\$\#\@\!\_\?'
    title = re.sub( r'[%s](?i)' % symbols, '', title )
    description = re.sub( r'[%s](?i)' % symbols, '', description )
    if title == description:
        return 1
    title = re.sub( r'[\d\s](?i)', '', title )
    description = re.sub( r'[\d\s](?i)', '', description )
    if title == description or title.find(description) > -1:
        return 1
    return 0

def uniqueValues( sequence ):
    """
        Removes duplicates from the list, preserving order of the items.

        Arguments:

            'sequence' -- Python list.

        Result:

            Python list.
    """
    if type(sequence) not in SequenceTypes:
        sequence = [sequence]
    return [ sequence[i] for i in range(len(sequence)) if sequence[i] not in sequence[:i] ]

def uniqueItems( mapping ):
    """
        Removes empty dictionary items.

        Arguments:

            'mapping' -- Python dictionary.

        Result:

            Python dictionary.
    """
    if type(mapping) not in MappingTypes:
        return mapping
    for key in tuple(mapping.keys()):
        if mapping[key]: continue
        del mapping[key]
    return mapping

# TODO
# * support all URL formats ( RFC1738, RFC2396, RFC2368 )
# * complete domains list
# * ftp.doma.in:/path/to/file
# * \\machine\path\to\file

_protos  = [ 'http', 'https', 'ftp', 'nntp' ]
_hostmap = { 'www':'http', 'ftp':'ftp', 'nntp':'nntp', 'news':'nntp' }
_domains = [ 'com', 'net', 'org', 'edu', 'gov', 'mil', 'biz', 'info', \
             'us', 'uk', 'ru', 'su', 'fr', 'de', 'nl', 'by', 'jp', 'tw' ]
_subst   = {
            'P' : '|'.join( _protos ),                  # protocol names
            'H' : '|'.join( _hostmap.keys() ),          # host prefixes
            'D' : '|'.join( _domains ),                 # top-level domains
            'C' : r'a-z0-9_\.\-\+\$\!\*\(\),\%\'',      # safe characters
            'N' : r'a-z0-9_\.\-',                       # hostname characters
            'A' : r'[a-z0-9_\.\-]+(?:\:\d+)?',          # host address
            'Q' : r'\?[^\s\[\]{}()]*',                  # query string
           }

_link_re = r'\b(%(P)s)://(?:[%(C)s]*(?:\:[%(C)s]*)?@)?%(A)s(?:/[%(C)s/~;]*)?(?:%(Q)s)?(?:#[%(C)s]*)?'
_host_re = r'\b(%(H)s)\d*\.%(A)s(?:/[%(C)s/~;]*)?\b'
_zone_re = r'\b[%(N)s]+\.(%(D)s)(?:\:\d+)?(?:/[%(C)s/~;]*)?\b'
_mail_re = r'\b(mailto):(?:(?:[%(C)s]+(?:@%(A)s)?,?)+(?:%(Q)s)?|%(Q)s)'
_addr_re = r'\b([%(C)s]+@%(A)s)\b'
_news_re = r'\b(news):(?:[%(C)s]+|\*)\b'

_url_res = [ _url_re % _subst for _url_re in _link_re, _host_re, _zone_re, _mail_re, _addr_re, _news_re ]
_url_rec = re.compile( '(?:' + '|'.join( _url_res ) + ')', re.I )
_eol_rec = re.compile( r'\r*\n' )

def formatPlainText( text, target=None ):
    """
        Converts plain text to HTML code, inserting hypertext links.

        Lines in the source text become separated with BR tags,
        tabulations and continuous whitespace are converted
        to the same amount of non-breaking spaces for the text
        to retain its formatting.  Special HTML characters are
        replaces with entity references.

        The function also extracts links to external resources
        from the text and replaces them with HTML tags.

        Arguments:

            'text' -- the source text

            'target' -- optional name of the target frame
                        for the links

        Result:

            String containing HTML text.
    """
    parts = []
    match = _url_rec.search( text )

    while match:
        href = link = escape( match.group(0) )

        if match.group(2): # _host_re
            href = '%s://%s' % ( _hostmap[ match.group(2).lower() ], href )
        elif match.group(3): # _zone_re
            href = 'http://%s' % href
        elif match.group(5): # _addr_re
            href = 'mailto:%s' % href

        if target and ( match.group(1) or match.group(2) or match.group(3) ):
            subst = '<a href="%s" target="%s">%s</a>' % ( href, target, link )
        else:
            subst = '<a href="%s">%s</a>' % ( href, link )

        parts.append( escape( text[ :match.start() ] ) )
        parts.append( subst )

        text = text[ match.end(): ]
        match = _url_rec.search( text )

    parts.append( escape( text ) )
    text = ''.join( parts )
    text = text.expandtabs()
    text = text.replace('  ', '&nbsp; ').replace('  ', ' &nbsp;')
    text = _eol_rec.sub('<br />\n', text)
    return text

def formatFloat( x ):
    """
        Converts float to truncated string
    """
    c,d = divmod( x, 1 )
    return d > 0 and '%.2f' % x or int(x)

def formatComments( text, mode=None ):
    """
        Converts comments text to formatted HTML code
    """
    if not text:
        return ''
    if not mode:
        text = re.sub(r'<p(.*?)>(?i)', '', text)
        text = re.sub(r'</p>(?i)', '<br>', text)
    elif mode == 1:
        # for tasks' description only
        text = re.sub(r'(<div class=)comments(>)(?i)', r'\1description\2', text)
    return text.strip()

def getPlainText( HTML, no_br_only=None ):
    """
        Returns formatted plain text from HTML code
    """
    if not HTML: return ''
    if no_br_only:
        HTML = re.sub(r'<br>(?i)', '', HTML)
        return HTML.strip()
    else:
        HTML = re.sub(r'>[\s]*<', '> <', HTML)
        HTML = re.sub(r'<style.*?>(.*?)</style>(?is)', '', HTML)
        HTML = re.sub(r'<script.*?>(.*?)</script>(?is)', '', HTML)
        HTML = re.sub(r'<br[\s\/]*?>(?i)', '\n', HTML)
        HTML = re.sub(r'</(p|li)>(?i)', '\n', HTML)
        HTML = re.sub(r'&nbsp;(?i)', ' ', HTML)
        rfrom = re.compile( r'<.*?>', re.I+re.DOTALL )
    return rfrom.sub(r'', HTML).strip()


_body_start_re = re.compile( r'\A.*<body\b.*?>\s*',  re.I + re.S )
_body_end_re = re.compile( r'\s*</body\b.*?>.*\Z', re.I + re.S )

def extractBody( text ):
    """
        Returns text inside BODY tag of HTML document.

        Arguments:

            'text' -- source string

        Result:

            String.
    """
    return _body_end_re.sub( '', _body_start_re.sub( '', text, 1 ), 1 )

def joinpath( *parts ):
    """
        Join two or more pathname components, inserting path
        delimiters as needed.

        The components can be either a string or a list of strings.
        If the first component is an empty string the path is considered
        absolute and is prepended with a single delimiter.  Any other
        empty component is ignored.

        Arguments:

            '*parts' -- arbitrary amount of path components

        Result:

            Path string.
    """
    path = []
    for part in parts:
        if type( part ) in ( TupleType, ListType ):
            path.extend( part )
        else:
            if not path and (not part or part.startswith('/')):
                path.append( '' )
            #part = part.strip('/') # python 2.2
            while part.startswith('/'): part = part[ 1:   ]
            while part.endswith('/'):   part = part[  :-1 ]
            if part:
                path.append( part )
    
    return '/'.join( path ) or (path and '/' or '')

def makepath( *args ):
    return minimalpath( normpath( joinpath( package_home( globals() ), *args ) ) )

_package_prefix = '.'.join( __name__.split('.')[:-1] )
_module_suffixes = ['py','pyc','pyo']

def loadModules( package=None, names=MissingValue, skip=(), packages=False, refresh=False, raise_exc=True ):
    """
        Loads modules from the specified sub-package.

        Arguments:

            'package' -- name of the package to import, relative
                         to the product location

            'names' -- list of module names to load; if not given,
                       all modules in the package are loaded

            'skip' -- list of module names that should not be loaded;
                      used only when loading all modules (i.e. no 'names')

            'packages' -- whether to load subpackages (directories)
                          instead of modules (files); 'False' by default

            'refresh' -- perform reloading of the modules; 'False'
                         by default

            'raise_exc' -- whether to propagate import errors to the caller,
                           otherwise just log warning; 'True' by default

        Result:

            Mapping from module names to module objects.
    """
    if package is None:
        package = _package_prefix
    else:
        package = _package_prefix + '.' + package

    modules = {}
    namespace = globals()

    if names is MissingValue:
        # first import the package itself
        module = sys.modules.get( package )
        if module is None:
            try:
                module = __import__( package, namespace, None, ['__name__'] )
            except:
                if raise_exc:
                    raise
                logger.warning( "Cannot import package '%s'" % package, exc_info=True )
                return modules

        # get directory path of the imported package
        namespace = vars( module )
        path = package_home( namespace )
        names = {}

        # filter out hidden and non-python files
        for name in os.listdir( path ):
            # skip illegal and reserved names
            if name.startswith('_') or name.startswith('.'):
                continue
            if name in skip:
                continue

            # check whether the path is valid package or module
            subpath = os.path.join( path, name )
            if packages:
                if not os.path.isdir( subpath ):
                    continue

            else:
                if not os.path.isfile( subpath ):
                    continue
                name, ext = os.path.splitext( name )
                if ext[1:].lower() not in _module_suffixes:
                    continue

            names[ name ] = 1

        # we need hash because there can exist both source
        # and compiled representation of the same module
        names = names.keys()

    for name in names:
        fullname = package + '.' + name
        module = sys.modules.get( fullname )

        try:
            if module is None:
                # the module is not loaded yet
                module = __import__( fullname, namespace, None, ['__name__'] )

            elif refresh:
                # the module is already loaded and must be refreshed
                module = reload( module )

        except:
            if raise_exc:
                raise
            logger.warning( "Cannot import module '%s'" % name, exc_info=True )

        else:
            modules[ name ] = module

    #print 'loadModules', package, modules.keys()
    return modules

_metatype_map = {}
_reserved_attrs = ( '__doc__', '__ac_permissions__', 'security' )


def InitializeClass( klass, version=None ):
    """
        Superior replacement for the Zope class initialization method.

        This function does several additional things compared to regular
        class initialization:

          - builds '_class_tag' attribute from versions
            of current and base classes, needed by automated
            object update code

          - populates *meta_type* to class mapping used by
            'getClassByMetaType()' function

          - removes *unimplemented* interfaces or features
            from the list of supported by base classes ones

          - if 'Config.BindClassAttributes' variable is set,
            inherited attributes and methods are bound to this
            class's dictionary to improve performance

        Arguments:

            'klass' -- class object

            'version' -- optional version of the class; if omitted,
                         '_class_version' is used
    """
    _InitializeClass( klass )

    # setup metatype-to-class mapping for getClassByMetaType
    if klass.__dict__.has_key('meta_type'):
        _metatype_map[ klass.meta_type ] = klass

    # get class version
    version = version or getattr( klass, '_class_version', None ) or hash( tuple( dir(klass) ) )

    tags = [ str(version) ]
    for base in klass.__bases__:
        if hasattr( base, '_class_tag' ):
            tags.append( base._class_tag )

    # set version tag on the class
    klass._class_version = version
    klass._class_tag = hash( tuple(tags) )

    if klass.__dict__.has_key('__unimplements__'):
        unimplement( klass, klass.__unimplements__ )

    # prepare recursively expanded base classes list for applyRecursive
    BaseClassTypes = [ ClassType, ExtensionClass ] # 
    bases = list( klass.__bases__ )
    mark = { klass : 1 }
    idx = 0

    while idx < len(bases):
        x = bases[ idx ]
        if mark.has_key( x ):
            idx += 1
        #elif not issubclass( klass, x ):
        #    idx += 1
        else:
            mark[ x ] = 1
            blist = [ base for base in x.__bases__ if not mark.has_key( base ) \
                      and type(base) in BaseClassTypes
                     ]
            if blist:
                bases[ idx:idx ] = blist
            else:
                idx += 1

    if bases:
        setattr( Config.BasesRecursive, klass.__name__, bases )
        #logger.info( 'InitializeClass %s recursively expanded of:\n%s' % ( \
        #    klass.__name__, '\n'.join( [ str(x) for x in bases ] ) ) )

    if klass.__module__.startswith('Products.ExpressSuiteTools'):
        setattr( Config.AppClasses, klass.__name__, klass )

    if not Config.BindClassAttributes:
        return

    # bind inherited attributes and methods to the class dictionary
    bound = {}
    kdict = klass.__dict__
    bases = list( klass.__bases__ )

    while bases:
        base = bases.pop(0)
        bdict = base.__dict__
        attrs = []

        for attr, value in bdict.items():
            if kdict.has_key( attr ) or attr in _reserved_attrs:
                continue
            real = getattr( klass, attr, None )
            #if real is None:
            #    continue
            if type(real) in MethodTypes:
                real = real.im_func
            if value is real:
                setattr(klass, attr, value) #kdict[ attr ] = value
                attrs.append( attr )
                bound[attr] = 1

        if attrs:
            logger.info( 'InitializeClass %s inherited attributes from %s:\n%s' % ( \
                klass.__name__, base.__name__, '\n'.join( attrs ) ) )

        bases.extend( base.__bases__ )

    if bound:
        setattr(klass, 'class__bound_attributes', bound)

def unimplement( klass, features ):
    """
        Removes the given feature from the list of interfaces supported
        by the class.

        Arguments:

            'klass' -- class object

            'features' -- a list of unsupported features
    """
    implements = getImplementsOfInstances( klass )
    klass.__implements__ = _recurseUnimplement( implements, features )

def _recurseUnimplement( implements, features ):
    # unimplement() helper
    if type(features) is not TupleType:
        features = (features,)
    if type(implements) is TupleType:
        implements = filter( lambda i, f=features: i not in f, implements )
        implements = tuple([ _recurseUnimplement( i, features ) for i in implements ])
    elif implements in features:
        implements = ()
    return implements

def getClassByMetaType( meta_type, default=MissingValue ):
    """
        Returns class object by its *meta_type* name.

        The class must be initialized with 'InitializeClass()' first.
        If no class with given *meta_type* is found 'KeyError' is raised
        unless default value is given.

        Arguments:

            'meta_type' -- *meta_type* name

            'default' -- optional value to be returned if not class is found

        Result:

            Class object.
    """
    try:
        return _metatype_map[ meta_type ]
    except KeyError:
        if default is MissingValue:
            raise
        return default

def getClassName( klass ):
    """
        Returns full name of the klass (with module name).

        Arguments:

            'klass' -- class object of interest, or an instance
    """
    if not isinstance( klass, ClassTypes ):
        klass = klass.__class__

    return klass.__module__ + '.' + klass.__name__

def listClassBases( klass, recursive=True ):
    """
        Returns class ancestors.

        Arguments:

            'klass' -- class or instance object

            'recursive' -- optional boolean flag, indicating whether
                           base classes should be listed recursively

        Result:

            A list of class objects.
    """
    if type(klass) is StringType:
        # XXX Convert from string.
        raise NotImplementedError

    elif type(klass) not in ClassTypes:
        klass = klass.__class__

    bases = list( klass.__bases__ )
    if not recursive:
        return bases

    seen = {}
    while bases:
        base = bases.pop(0)
        bases.extend( base.__bases__ )
        seen[ base ] = 1

    return seen.keys()

try:
    isinstance( None, ExtensionClass )
except TypeError:
    pass #isInstance = _app_isinstance # python 2.1
else:
    isInstance = isinstance


def installPermission( klass, perm ):
    """
        Installs custom permission in the given *klass*.

        Inserts given permission into '__ac_permissions__' structure
        in the class.  This is needed for the permission to appear on
        the *Security* tab of ZMI.

        Arguments:

            'klass' -- class object

            'perm' -- permission name, string
    """
    ac_perms = getattr( klass, '__ac_permissions__', () )
    if perm not in filter( lambda p: p[0], ac_perms ):
        klass.__ac_permissions__ = ac_perms + ( (perm, ()), )

def isBroken( object, class_name=None ):
    """
        Checks whether existing persistent object is of broken
        (renamed or removed) class.

        Arguments:

            'object' -- any instance

            'class_name' -- original class name (optional), the object should
                            have previously been an instance of this class

        Result:

            Truth if the object is broken.
    """
    return isInstance( object, BrokenClass ) \
        and ( class_name is None or object.__class__.__name__ == class_name \
              or object.__class__.__module__.__name__ + '.' + object.__class__.__name__ == class_name )

def setSecurityManager( manager ):
    # sets a security manager, for the current thread
    thread_id = get_ident()
    old = SecurityManagers.get( thread_id, None )
    SecurityManagers[ thread_id ] = manager
    return old

_num_rec = re.compile( r'\s*\[(\d+)\]\s*$' )

def getNextTitle( title, items=() ):
    """
        Returns title with sequental number appended.

        The purposes of this function is to generate unique titles
        when several objects with the same title are added to the container.
        The returned title has a sequential number in square brackets
        appended to it.  If the title already contains a number it is
        incremented.

        Arguments:

            'title' -- the title string

            'items' -- optional list of already existing titles;
                    they are parsed to find the highest number

        Result:

            Title string with the number in brackets appended.
    """
    if title and title not in items:
        return title

    idx = len( items )
    match = _num_rec.search( title )
    if match:
        title = title[ :match.start() ]
        if int( match.group(1) ) > idx:
            idx = int( match.group(1) )

    for item in items:
        match = _num_rec.search( item )
        if match and int( match.group(1) ) > idx:
            idx = int( match.group(1) )

    return '%s [%d]' % ( title, idx + 1 )


# characters from ObjectManager.bad_id
#_bad_id_re = re.compile( r'[^a-zA-Z0-9-_~,.$\(\)# ]+' )
_bad_id_re = re.compile( r'[^a-zA-Z0-9-_~$# ]+' )
_words_sep_re = re.compile( r'[\s|_]+' )

def cookId( container, id=None, prefix='', suffix='', idx=0, title=None, size=20 ):
    """
        Generates a new object identifier, the best of all possible.

        New identifier is created from either denoted value,
        title of the object, or prefix with a sequetial number added.
        Generated identifier is checked against existing subobjects
        of the container to prevent duplication.  If the identifier
        is occupied, the number is incremented and the check is repeated.

        If neither 'id' nor 'prefix' nor 'title' is given,
        the returned value is a random '"objXXXXXXXXXX"' string.

        Arguments:

            'container' -- the target where new object will be placed

            'id' -- desired identifier, optional

            'prefix' -- prefix for the sequential identifier, optional

            'suffix' -- suffix for the sequential identifier, optional

            'idx' -- starting index for the sequential identifier, optional

            'title' -- optional title of the new object; not used if 'id' is given

            'size' -- the maximium length of the identifier in characters,
                    20 by default

        Result:

            New identifier string.
    """
    if id:
        id = _bad_id_re.sub( '_', id )

    elif title:
        lang = getToolByName( container, 'portal_membership' ).getLanguage()
        # XXX spaces are replaced with underscores here, but it's not always necessary
        id = translit_string( title.strip(), lang )
        id = _words_sep_re.sub( '_', id )
        if len(id) > size:
            # cut and split title into words, then drop clipped last word
            words = id[ :size+1 ].split('_')
            id = len(words) == 1 and words[0] or '_'.join( words[:-1] )
        id = _bad_id_re.sub( '_', id )

    if hasattr(container, '_checkId'):
        check_id = container._checkId
    else:
        assert hasattr(container, 'has_key'), "invalid container type"
        def check_id( id, container=container ):
            if container.has_key(id):
                raise DuplicateIdError

    if prefix == '_authenticated_':
        try: username = getToolByName( context, 'portal_membership' ).getAuthenticatedMember().getUserName()
        except: username = ''
        id = '%s_%s_%s' % ( strftime( '%Y%m%d%H%M%S', localtime() ), username, id )
        prefix = None
    elif prefix == '_localtime_':
        id = '%s_%s' % ( strftime( '%m%d%H%M%S', localtime() ), id )
        prefix = None

    if id:
        try:
            check_id( id )
        except DuplicateIdError:
            if not prefix:
                prefix = id
            id = None
        except InvalidIdError:
            id = None
        else:
            if not prefix:
                prefix = id

    elif prefix:
        prefix = _bad_id_re.sub( '_', prefix )

    while not id:
        if prefix:
            if prefix in ['entry']:
                idx += 1
                id = '%s_%05d%s' % ( prefix, idx, suffix )
            else:
                idx += 1
                id = '%s_%03d%s' % ( prefix, idx, suffix )

        else:
            id = 'obj%010u' % ( randrange(1000000000) )

        try: check_id( id )
        except ( DuplicateIdError, BadRequestException ): id = None

    return id

def TypeOFSAction( context, cb_copy_data=None, REQUEST=None ):
    """
        Returns type of cut/copy action with clipboard
    """
    if cb_copy_data is None:
        if REQUEST is None:
            REQUEST = check_request( context, REQUEST )
        cb_copy_data = REQUEST and REQUEST.get('__cp')
        if cb_copy_data is None:
            return None

    try: decoded = _cb_decode( cb_copy_data )
    except: return None

    op = decoded[0]
    return op

def listClipboardObjects( context, permission=None, cb_copy_data=None, REQUEST=None ):
    """
        Return a list of objects in the clipboard for which current user
        has required permission.

        Positional arguments:

            'context' -- an object inside the portal; needed to acquire
                    application root

            'permission' -- optional permission name (*View* by default)
                    the current user must have on the objects, inaccessible
                    objects are not included in the result

        Keyword arguments:

            'cb_copy_data' -- clipboard data; if not given, 'REQUEST'
                    or 'context' is used to obtain the data

            'REQUEST' -- Zope request object

        Result:

            The list of objects, may be empty.
    """
    oblist = []

    if cb_copy_data is None:
        if REQUEST is None:
            REQUEST = check_request( context, REQUEST )
        cb_copy_data = REQUEST and REQUEST.get('__cp')
        if cb_copy_data is None:
            return oblist

    try: decoded = _cb_decode( cb_copy_data )
    except: return oblist

    op = decoded[0]
    app = context.getPhysicalRoot()

    if permission is None:
        permission = CMFCorePermissions.View

    for mdata in decoded[1]:
        m = loadMoniker( mdata )

        try: ob = m.bind( app )
        except: continue

        if _checkPermission( permission, ob ):
            oblist.append( ob )

    return oblist

def get_param( name, REQUEST, kw, default=MissingValue ):
    """
        Retrieves the parameter from either request or dictionary.

        Arguments:

            'name' -- the name of the parameter

            'REQUEST' -- Zope request object

            'kw' -- dictionary for additional 'name' lookup
                    if the parameter is absent from the 'REQUEST'

            'default' -- optional default value to be returned
                    if the parameter is not found

        Result:

            The list of objects, may be empty.

        Exceptions:

            'KeyError' -- the requested parameter is not found
            and default value is not given.
    """
    value = None
    IsError = 0
    if REQUEST is not None:
        try: value = REQUEST[ name ]
        except KeyError:
            IsError = 1
    if value is None and kw:
        try: value = kw[ name ]
        except KeyError:
            IsError = 1
    if default is not MissingValue:
        if default is None:
            pass
        else:
            default_type = type(default)
            value_type = type(value)
            if value and value_type != default_type:
                if default_type in SequenceTypes and value_type not in SequenceTypes:
                    value = [value]
    elif IsError:
        raise KeyError, name
    return value or default

def extractParams( mapping, request, *names ):
    # returns values from the form
    values = []
    for name, value in request.form.items():
        mapping.setdefault( name, value )
    for name in names:
        if mapping.has_key( name ):
            values.append( mapping[ name ] )
            del mapping[ name ]
        else:
            values.append( None )
    if len(names) == 1:
        return values[0]
    return values

def addQueryString( _url='', _params=None, _fragment=None, **kw ):
    """
        Adds query parameters to the URL string.

        The parameters are taken from three sources in the following
        priority order:  keyword arguments first, then dictionary, and
        existing parameters in the URL in the last place.

        List of tuple values are converted to a *tokens* Zope type.
        'None' values are never included in the result.

        Positional arguments (optional):

            'url=""' -- the URL, may itself contain parameters;
                        empty string is used by default

            'params' -- dictionary mapping parameter names to values

            'fragment' -- URL fragment name, which is added to the result
                          along with the "#" character

        Keyword arguments (optional):

            '**kw' -- additional parameters as name=value pairs

        Result:

            URL string with embedded parameters.
    """
    if _params:
        for name, value in _params.items():
            kw.setdefault( name, value )

    if _url:
        parts = _url.split( '?', 1 )
        result = parts.pop(0)
        if parts:
            # parse query params from url to override with kw params
            for part in parts[0].split('&'):
                name, value = part.split( '=', 1 )
                kw.setdefault( unquote(name), unquote(value) )
    else:
        result = _url

    parts = []

    for name, value in kw.items():
        if value is None:
            continue

        if type(value) in [ ListType, TupleType ]:
            name += ':tokens'
            value = ' '.join( map( str, value ) )

        parts.append( quote(name) + '=' + quote(str(value)) )

    if parts:
        result += '?' + '&'.join( parts )

    if _fragment is not None:
        result += '#' + _fragment

    return result

def getPublishedInfo( context, REQUEST ):
    # returns extended information about what was published
    # first try to return cached result
    try: return REQUEST['PUBLISHED_INFO']
    except KeyError: pass

    published = REQUEST.get('PUBLISHED')
    path_info = REQUEST.get('PATH_INFO', '').strip()
    has_slash = path_info.endswith('/')
    path_id = splitpath( normpath( path_info ) )[1]
    base = aq_base(published)
    base_type = type(base)
    object = None

    is_method = base_type in MethodTypes
    if is_method:
        object = published.im_self

    elif base_type in ( FSDTMLMethod, FSPythonScript ):
        p_id = published.getId()
        object = aq_parent( published )
        if p_id != path_id:
            try:
                path_id = object.getId()
            except:
                path_id = getattr(object, 'id', None)
            if not path_id:
                object = None
        else:
            is_method = 1

    if object is None:
        if hasattr( base, 'implements' ):
            is_method = 0
        elif getattr( base, 'isDocTemp', None ):
            is_method = 1
        elif hasattr( base, 'func_code' ):
            is_method = 1
        if is_method:
            object = aq_parent( published )
        else:
            object = published

    principal = REQUEST.get( ( id(aq_base(object)), 'principal' ), object )
    subpath = REQUEST.get( ( id(aq_base(principal)), 'subpath' ) )
    is_subitem = not not subpath

    if not is_subitem:
        principal = aq_parent(aq_inner( object ))
        subpath = REQUEST.get( (id(aq_base(principal)), 'subpath') )
        if not subpath:
            principal = object

    info = ( published, object, is_method, path_id, has_slash, principal, subpath, is_subitem )
    REQUEST.set( 'PUBLISHED_INFO', info )

    return info

def refreshClientFrame( sections, REQUEST=None ):
    """
        Sets an indicator in the request object that named section of the user interface needs to be refreshed.

        The real update is initiated by a JavaScript variable 'updateSections' which is set to the list of section names
        in the page header.

        The list of sections that need to be refreshed is saved during external redirection as an '_UpdateSections' query
        parameter.  If *workspace* needs to be refreshed then the issued redirection points to a *reload_frame* page which
        loads requested link into the *workspace* frame.

        Arguments:

            'sections' -- the section name such as '"workspace"' or those defined in the *menu.dtml*, List

            'REQUEST' -- Zope request object; retrieved with 'get_request()' if not specified
    """
    if REQUEST is None:
        REQUEST = get_request()
    if REQUEST is None:
        return
    if not type(sections) is ListType:
        sections = [ sections ]
    if 'workspace' in sections:
        REQUEST.set( '_UpdateWorkspace', 1 )
        sections.remove( 'workspace' )
    if not sections:
        return

    updated = REQUEST.get( '_UpdateSections' ) or []
    if not updated:
        updated = sections
    else:
        for x in sections:
            if x not in updated:
                updated.append( x )

    REQUEST.set( '_UpdateSections', updated )

def checkCommand( command ):
    """
        Checks whether a given system command can be found
        in 'PATH' and is executable.

        Arguments:

            'command' -- system command name without path
                         and '".exe"' extension

        Result:

            Truth value if command is found and is executable.
    """
    path = os.environ.get('PATH') or os.defpath

    for prefix in path.split( os.pathsep ):
        if os.access( prefix + os.sep + command, os.X_OK ) or \
            os.access( prefix + os.sep + command + '.exe', os.X_OK ):
            return 1

    return 0

def encodeMapping( mapping ):
    # encodes mapping to a base64 string
    encoded = base64.encodestring( marshal.dumps( mapping ) )
    return encoded.strip().replace( '\n', '' )

def decodeMapping( encoded ):
    # decodes a base64 string to a mapping
    mapping = {}
    if encoded:
        mapping.update( marshal.loads( base64.decodestring( encoded ) ) )
    return mapping

def parseTitle( s, size=500 ):
    """
        Returns stripped Title string for new object.
        Used by portal catalog
    """
    v = str(s)
    ddd = '...'
    n = 3
    if not v or size <= n:
        return ddd
    p = len(v) > size and ddd or ''
    if p:
        v = v[:size]
    while len(v) > size - len(p):
        l = v.rfind(' ')
        if l > -1:
            v = v[:l]
        else:
            break
    return v + p

def parseString( value, size=None ):
    """
        Returns valid query cooked string
    """
    if not value:
        return ''
    if type(value) in ( ListType, TupleType ):
        x = ' '.join([ str(x).strip() for x in value if x ])
    else:
        x = str(value)
    x = x.strip()
    if size and len(x) > size:
        x = x[0:size]
    x = re.sub(r'[\|\f\r\t\v\n\\\{\}\[\]\(\)]+', r'', x)
    x = re.sub(r'[\']+', r'_', x) #\"
    #x = re.sub(r'[\/]+', r' ', x)
    return x

_month_day_rec = re.compile( r'\A(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})' )

def parseDate( name, REQUEST, default=MissingValue ):
    """
        Returns a date value from the submitted HTML form.

        The form may contain either a single field for date string
        or three separate fields for year, month and day. In the latter
        case the field names should have '"_year"', '"_month"' and '"_day"'
        suffixes respectively.

        The entered values are extracted from the request and converted
        to a 'DateTime' object.

        Positional arguments:

            'name' -- name of the date field or fields

            'REQUEST' -- Zope request object

            'default' -- optional value that is returned if valid date cannot be returned

        Result:

            DateTime object of default value.

        Exceptions:

            'KeyError' -- the request does not contain required
            fields and no default value is given

            'DateTime.SyntaxError' -- the date string cannot be parsed
    """
    date = REQUEST.get( name )
    if date is not None:
        if type(date) is StringType:
            date = _month_day_rec.sub( r'\3/\2/\1', date ) # YYYY/MM/DD
        elif type(date) is type(DateTime()):
            return date
    else:
        try:
            date = '%s/%s/%s' % ( REQUEST[ '%s_year'  % name ],
                                  REQUEST[ '%s_month' % name ],
                                  REQUEST[ '%s_day'   % name ] )
        except KeyError:
            pass

    if not date:
        if default is MissingValue:
            raise KeyError, name
        return default

    try:
        return DateTime( date )
    except:
        if default is MissingValue: return DateTime()
        return default

def parseDateValue( value, mapping=MissingValue, default=MissingValue ):
    """
        Returns a date value from the submitted HTML form.

        The form may contain either a single field for date string
        or three separate fields for year, month and day. In the latter
        case the field names should have '"_year"', '"_month"' and '"_day"'
        suffixes respectively.

        The entered values are extracted from the request and converted
        to a 'DateTime' object.

        Positional arguments:

            'value' -- either string, record, or name of the date field;
                       in the latter case 'mapping' argument must present

            'mapping' -- optional mapping or Zope request object

            'default' -- optional value that is returned if valid
                         date cannot be returned

        Result:

            'DateTime' object of default value.

        Exceptions:

            See 'parseDateTime' function.
    """
    if type(value) is StringType and mapping is not MissingValue:
        name = value
        try:
            if mapping.has_key( name ):
                value = mapping[ name ]
                if not value:
                    raise KeyError, name
            else:
                value = { 'year'  : mapping[ '%s_year'  % name ],
                          'month' : mapping[ '%s_month' % name ],
                          'day'   : mapping[ '%s_day'   % name ] }
        except KeyError:
            if default is not MissingValue:
                return default
            raise KeyError, name

    # XXX needed for type converter
    if type(value) is StringType and not len(value.strip()):
        if default is not MissingValue:
            return default
        return None

    return parseDateTime( value, default, time=False )

def parseTime( name, REQUEST, default=MissingValue ):
    """
        Returns a time interval value from the submitted HTML form.

        The form may have up to three fields (for number of days,
        hours, and minutes) combined into *record* type.  The fields
        should be named with the base record name and '"days"', '"hours"'
        and '"minutes"' suffixes respectively.

        The entered values are extracted from the request and converted
        to a single number of seconds.

        Arguments:

            'name' -- base name of the record fields

            'REQUEST' -- Zope request object

            'default' -- optional value that is returned if specified
                         record is not found in the request

        Result:

            Number of seconds or default value.

        Exceptions:

            'KeyError' -- the request does not contain required fields
            and default value is not specified
    """
    record = REQUEST.get( name )
    if not record:
        if default is MissingValue:
            raise KeyError, name
        return default

    days = record.get( 'days',    0 )
    hours = record.get( 'hours',   0 )
    minutes = record.get( 'minutes', 0 )

    return days*86400 + hours*3600 + minutes*60

_month_day_re = re.compile( r'\A(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})' )
_date_items = ['year','month','day']
_time_items = ['hour','minute']
_extra_items = ['second']


def parseDateTime( value, default=MissingValue, time=True ):
    if value is None and default is not MissingValue:
        return default

    # XXX needed for type converter
    if type(value) is StringType and not len(value.strip()):
        if default is not MissingValue:
            return default
        return None

    if isinstance( value, DateTime ):
        return time and value or value.earliestTime()

    if type(value) is StringType:
        args = [ _month_day_re.sub( r'\3/\2/\1', value ) ] # YYYY/MM/DD

    else:
        try:
            # may raise KeyError if key does not exist
            args = [ value[i] for i in _date_items ]
        except ( AttributeError, TypeError ):
            raise TypeError, 'string or mapping required'

        if time:
            # may raise KeyError if some key does not exist
            args.extend( [ value[i] for i in _time_items ] )

        for i in _extra_items:
            try: args.append( value[i] )
            except KeyError: pass

        try:
            # parse strings into integers
            args = map( int, args )
        except ValueError:
            pass # try DateTime conversion anyway

    try:
        value = DateTime( *args )
    except ( DateTime.SyntaxError, DateTime.DateTimeError ):
        if default is not MissingValue:
            return default
        raise

    return time and value or value.earliestTime()

def getObjectByUid( context, uid, implements=None, restricted=None ):
    """
        Returns an object inside the portal by given uid
    """
    catalog = getToolByName( context, 'portal_catalog', None )
    if catalog is None:
        return None
    if not restricted:
        return catalog.unrestrictedGetObjectByUid( uid, implements )
    else:
        return catalog.getObjectByUid( uid, implements )

def UnrestrictedCheckObject( context, ob=None ):
    """
        Checks the object in the catalog and returns one back
    """
    catalog = getToolByName( context, 'portal_catalog', None )
    uid = None
    try:
        if ob is not None:
            uid = ob.getUid()
        ob = catalog.unrestrictedGetObjectByUid( uid ) or ob
    except:
        logger.error( 'Utils.UnrestrictedCheckObject cannot check object, uid: %s, ob: %s' % ( \
            uid, `ob` ), exc_info=True )
    return ob

def applyRecursive( method, reverse, object, *args, **kw ):
    """
        Recursively invokes the method for each class
        in the object's inheritance hierarchy.

        Arguments:

            'method' -- reference to the unbound method

            'reverse' -- indicates that classes should be invoked in reverse (in the opposite) direction

            'object' -- target object for the method

            '*args', '**kw' -- additional arguments to be passed to
                               the invoked method

        Note:

            Methods are invoked only for classes inherited
            from the method's containing class.  The order of
            processing base classes is left-to-right, depth-first.
    """
    name = method.__name__
    klass = method.im_class
    args = ( object, ) + args

    bases = [ object.__class__ ]
    bases[:-1] = getattr( Config.BasesRecursive, object.__class__.__name__, [] )
    if reverse:
        bases.reverse()

    #logger.info( 'applyRecursive object [%s], class [%s], inherited method [%s] from classes %s' % ( \
    #    object, klass.__name__, name, bases ) )

    for base in bases:
        if not issubclass( base, klass ):
            continue
        # skip methods bound by InitializeClass
        bound = getattr( base, 'class__bound_attributes', None )
        if bound and bound.has_key( name ):
            continue
        # call method from the base class if exists
        if not base.__dict__.has_key( name ):
            continue
        try:
            #logger.info( 'applyRecursive base [%s], name [%s]' % ( base, name ) )
            apply(getattr( base, name ), args, kw)
        except ( ConflictError, ReadConflictError ):
            raise
        except:
            logger.error( 'Utils.applyRecursive unexpected error, method: %s, base: %s' % ( \
                name, `base` ), exc_info=True )
            raise

def getClientStorageType( context=None ):
    """
        Returns current user's storage type
    """
    archive = 0
    if context is None: return archive

    try:
        properties = getToolByName( context, 'portal_properties', None )
        user_storage_type = properties.storage_type()

        if user_storage_type == 'archive':
            archive = 1
        elif user_storage_type == 'storage':
            archive = 0
        else:
            archive = None
    except ( TypeError, ValueError ):
        archive = 0

    return archive

class File( FSImage ):
    """
        Filesystem File
    """
    meta_type = 'Filesystem File'

    def _readFile( self, reparse ):
        data = FSImage._readFile( self, 0 )

        # XXX workaround for CMF-1.3-beta bug (doesn't read .properties)
        ext = splitext( self._filepath )[1]
        if ext.startswith( '.' ):
            ext = ext[ 1: ]

        ctype = Config.FileExtensionMap.get( ext.lower() ) or Config.DefaultAttachmentType
        self.setContentType( ctype )
        return data

    def setContentType( self, ctype ):
        self.content_type = ctype

registerMetaType( 'File', File )
#for _ext in Config.FileExtensionMap.keys():
#    registerFileExtension( _ext, File )

try:
    from BTrees.IIBTree import multiunion
except ImportError: # Zope < 2.6
    multiunion = None

def multiintersection( seq ):
    if not len(seq):
        return seq
    return reduce( intersection, seq )

if multiunion is None:
    def multiunion( seq ):
        if not len(seq):
            return seq
        return reduce( union, seq )

def translate( context, text, lang=None ):
    """
        Translates a string to the current language.

        Arguments:

            'context' -- an object through which the portal message
                         catalog can be acquired

            'text' -- the string to be translated

            'lang' -- optional target language code, by default
                      the currently selected language is used

        Result:

            Translated string.
    """
    if not text:
        return ''
    try: return getToolByName(context, 'msg').gettext(text, lang=lang, add=0)
    except: return text

def CheckAntiSpam( context, member_id=None, brains_type=None ):
    """
        Checks antispam mail mode for given member
    """
    prptool = getToolByName( context, 'portal_properties', None )
    if prptool is None:
        return 0

    email_antispam = prptool.getProperty('email_antispam')
    IsAntiSpam = email_antispam and 1 or 0
    if not IsAntiSpam:
        return 0

    membership = getToolByName( context, 'portal_membership', None )
    if membership is None or not member_id:
        return 1

    try: 
        login_time = membership.getMemberActivity( member_id )
        if not login_time:
            return 1

        followup = getToolByName( context, 'portal_followup', None )
        if followup is None:
            return 0

        days = DateTime() - login_time
        if days < 5 and followup.countPendingTasksForUser( member_id, brains_type ) < 10:
            IsAntiSpam = 0
    except: pass

    return IsAntiSpam

def getRelativeURL( context, clean=None ):
    """
        Returns object relative URL to store a object between portal storages (storage <-> archive)
    """
    url = context.physical_path()
    instance = GetInstance( context )
    if clean and url and instance:
        url = url.replace( '/'+instance, '' )
    return url

def getBTreesItem( item ):
    """
        Returns BTrees item copy as a dictionary
    """
    if not item:
        return None
    value = {}
    for key in item.keys():
        value[key] = item[key]
    return value

def parseMemberIDList( context, ids=None, check_delegate=None, check_access=None ):
    """
        Returns plain users list, expanding included groups
    """
    if not ids or context is None:
        return []

    membership = getToolByName( context, 'portal_membership', None )
    try:
        instance = getToolByName( context, 'portal_properties' ).instance_name()
    except:
        instance = None
        raise
    users = []
    res = []

    for id in ids:
        # Parse groups only
        if id.startswith('group:'):
            group_id = id[6:]
            members = FilterMembersByDefaultAccess( context, membership.listGroupMembers( group_id, member=1 ) )
            group_users = [ x.getUserName() for x in members ]
            if group_users:
                IsDAGroup = membership.getGroupAttribute( group_id, attr_name='DA' )
                if check_delegate:
                    res.append( { 'id' : id, 'type' : IsDAGroup and 'any' or 'all', 'members' : tuple(group_users) } )
                else:
                    for user in group_users:
                        if user not in res:
                            res.append( user )
            continue

        """ check if member has default access """
        if check_access and instance:
            member = membership.getMemberById( id )
            if member is None or not member.getMemberAccessLevel( instance ):
                continue

        # Parse members
        if check_delegate:
            users.append( id )
        elif id not in res:
            res.append( id )

    if check_delegate and users:
        res.append( { 'id' : 'users', 'type' : 'all', 'members' : users } )

    return filter(None, res) or []

# ================================================================================================================

def UpdateRolePermissions( context, userid=MissingValue, roles=MissingValue ):
    """
        Here we're setting given member roles for a object and at once updating mapping workflow permissions.
        Otherwise, we cannot get access to the object in accordance with current state permission settings.

        We should run updateRoleMappingsFor method.
    """
    if context is None:
        return
    if userid is not MissingValue:
        if userid is not None:
            if type(roles) is not ListType:
                roles = [ roles ]
            context.manage_setLocalRoles( userid, roles )
    try:
        wf = context.getCategory().getWorkflow()
    except:
        wf = None
    if wf is None:
        return
    wf.updateRoleMappingsFor( context )

def copy_is_allowed( context, id ):
    """
        Checks if copying of the object allowed
    """
    IsAllowed = 1
    try:
        ob=context._getOb(id)
        review_history=context.portal_workflow.getInfoFor(ob, 'review_history')
    except:
        logger.error( 'Utils.copy_is_allowed bad object: %s, context [%s]' % ( \
            id, context.physical_path() ), exc_info=True )
        return 0
    if not review_history or len(review_history) < 5:
        pass
    else:
        copies = 0
        for x in review_history:
            if x.has_key('state') and x['state'] == 'evolutive':
                copies += 1
        if copies > 1:
            IsAllowed = 0
    if not IsAllowed:
        logger.info( 'Utils.copy_is_allowed *NO*: %s, context [%s]' % ( id, context.physical_path() ) )
    return IsAllowed

def CreateObjectCopy( context, item, default=None ):
    """
        Creates custom object copy instead of paste
    """
    if context is None or item is None:
        return None

    pt = getToolByName( context, 'portal_types', None )
    allowed_types = pt is not None and pt.listContentTypes( context ) or []

    if not 'HTMLDocument' in allowed_types:
        return None

    title = item.Title()
    cat_id = item.Category()

    metadata = getToolByName( context, 'portal_metadata', None )
    category = metadata is not None and metadata.getCategoryById(cat_id) or None
    if category is None:
        return 0

    id = cookId( context, prefix='_localtime_', title=title, size=20 )
    context.invokeFactory( 'HTMLDocument', id )

    obj = context[ id ]
    if obj is None:
        return 0

    membership = getToolByName( context, 'portal_membership', None )
    member = membership.getAuthenticatedMember()

    obj.setTitle( title )
    obj.setDescription( item.Description() )
    obj.setObjectLanguage( item.Language() )
    obj.setCategory( cat_id )

    for attr in category.listAttributeDefinitions():
        name = attr.getId()
        if default and attr.haveComputedDefault():
            value = attr.getDefaultValue()
            if attr.isReadOnly():
                if name.lower().endswith('department'):
                    try:
                        value = type(value) in SequenceTypes and len(value) > 1 and value[1] or value or \
                            member.getMemberDepartment()
                    except: pass
            elif type(value) in SequenceTypes and len(value) > 1:
                value = item.getCategoryAttribute( name ) or ['nonselected']
        else:
            value = item.getCategoryAttribute( name )
        obj.setCategoryAttribute( name, value, reindex=0 )

    try:
        copy_clipboard = membership.getInterfacePreferences('copy_clipboard') or 0
        setattr(obj, 'creators', (member.getUserName(),))
    except:
        copy_clipboard = 0

    clean = 1
    if copy_clipboard:
        for id, ob in item.listAttachments():
            if ob is None:
                continue
            try:
                title = ob.Title()
                file = ob.RawBody()
                obj.addFile( id=id, file=file, title=title )
                clean = 0
            except: pass

    html = obj.check_attachments_visibility( getattr(item, 'text'), clean=clean )
    Document._edit( obj, html )

    setattr( obj, 'selected_template', getattr( item, 'selected_template' ) )
    obj.reindexObject()

    return 1

def makeTuple( *args ):
    """ For Python compatibility we should check 'Tuple' type (!). Why? :-/ """
    res = []
    for x in args:
        if not x: continue
        if not type(x) in SequenceTypes:
            res.append( x )
        else:
            res.extend( [ i for i in x if x ] )
    return tuple( res )

def getContainedObjects( object, path=None, recursive=None, followup=None ):
    """
        Returns all objects are collected inside the given container
    """
    obs = []
    if object is None:
        pass
        
    elif followup:
        try:
            if object.followup is not None:
                obs.extend( object.followup.getBoundTasks( recursive=1 ) )
        except: pass

    elif getattr(object, 'meta_type', None) == 'HTMLDocument':
        if recursive:
            obs = [ object ]
        # versions
        if getattr(object, 'version', None) is not None:
            versions = object.version.objectValues()
            obs.extend( versions )
        else:
            versions = []
        # tasks
        if getattr(object, 'followup', None) is not None:
            tasks = object.followup.getBoundTasks( recursive=1 )
            obs.extend( tasks )
        else:
            tasks = []
        # discussions
        if getattr(object, 'talkback', None) is not None:
            obs.extend( object.talkback.objectValues() )
        for ob in object.objectValues():
            if getattr(ob, 'meta_type', None) == 'HTMLDocument':
                obs.append( ob )
                obs.extend( ob.version.objectValues() )
        # attachments
        i = 0
        l = len(obs)
        while i < l:
            ob = obs[i]
            for id, x in ob.objectItems():
                if getattr(x, 'meta_type', None) in Config.AttachmentTypes:
                    obs.append( x )
            i += 1

    if not path:
        return obs
    return [ ( x, '/'.join(x.getPhysicalPath()) ) for x in obs ]

def FilterMembersByDefaultAccess( context, members=None ):
    """
        Returns (filtered) members list gaved access for current portal instance
    """
    try:
        instance = getToolByName( context, 'portal_properties' ).instance_name()
        return filter(None, [ x for x in members if x.getMemberAccessLevel( instance ) ]) or []
    except:
        pass
    return []
