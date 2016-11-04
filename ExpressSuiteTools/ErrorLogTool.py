"""
Defines ErrorLogTool class - portal error logging and reporting tool.
$Id: ErrorLogTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 10/12/2007 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import Zope2
from zLOG import LOG, DEBUG, TRACE, INFO, ERROR

from sys import exc_info
from time import strftime, localtime

from AccessControl import ClassSecurityInfo
from AccessControl.SecurityManagement import getSecurityManager
from AccessControl.User import nobody
from Acquisition import aq_inner, aq_parent, aq_get

import transaction
from ZODB.Connection import ConflictError

try:
    from persistent.list import PersistentList
except ImportError:
    PersistentList = None

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.ActionProviderBase import ActionProviderBase
from Products.CMFCore.Expression import Expression
from Products.CMFCore.utils import UniqueObject, getToolByName, _checkPermission

try:
    from Products.SiteErrorLog.SiteErrorLog import SiteErrorLog
except ImportError:
    # XXX recall why SimpleItem is needed
    from OFS.SimpleItem import SimpleItem as SiteErrorLog

import Config
from Config import Permissions
from Exceptions import SimpleError, Unauthorized, formatErrorValue, formatException
from SimpleObjects import ToolBase

from Utils import InitializeClass


class ErrorLogTool( ToolBase, SiteErrorLog ):
    """
        Portal error logging tool.

        Basically this tool replicates behaviour of the 'error_log' object
        of Zope (which it is based on) with additional improvements over it,
        namely the ability to send report to the administrator or product
        support by e-mail, extended exception information and persistent log
        entries.

        Each error log entry is a dictionary containing exception
        and environment information. All entries are stored in the single
        persistent list, limited to Config.MaxErrorLogEntries in length.

        Only available under Zope >= 2.6.
    """
    _class_version = 1.0

    id = 'portal_errorlog'
    meta_type = 'ExpressSuite ErrorLog Tool'

    security = ClassSecurityInfo()

    manage_options = SiteErrorLog.manage_options + ActionProviderBase.manage_options

    keep_entries = Config.MaxErrorLogEntries
    _ignored_exceptions = ( 'Unauthorized', 'NotFound', 'Redirect' )

    def _initstate( self, mode ):
        #
        # Initialize attributes.
        #
        if not ToolBase._initstate( self, mode ):
            return 0

        if not ( hasattr( self, '_log' ) or PersistentList is None ):
            self._log = PersistentList()

        return 1

    def raising( self, info ):
        """
            Logs an exception.

            Called by exception handler (see Zope.zpublisher_exception_hook)
            if python exception is generated during handling the request.

            Appends collected exception and environment information to the
            error log. Ignores unauthorized exceptions for anonymous requests.

            Arguments:

                'info' -- tuple with the exception information
                          (type, value, traceback)

            Result:

                Absolute URL of the corresponding error log entry page.
        """
        etype, value, tb = info
        REQUEST = aq_get( self, 'REQUEST', None )

        if REQUEST is not None:
            # ignore anonymous requests
            if etype is Unauthorized and not REQUEST._auth:
                return None
            # try to authenticate user
            # XXX will this work with cookie auth???
            if REQUEST._auth \
                    and etype in [ 'Debug Error', 'NotFound', 'Forbidden' ] \
                    and getSecurityManager().getUser() is nobody:
                try: REQUEST.clone().traverse( self.physical_path() )
                except: pass

        tb = formatException( etype, value, tb )
        url = SiteErrorLog.raising( self, (etype, value, tb) )
        if url is None:
            return None # ignored exception

        log = self._getLog()
        entry = log[-1] # XXX race condition

        entry['time_str'] = strftime( '%Y-%m-%d %H:%M:%S', localtime( entry['time'] ) )

        try: entry['value'] = str( formatErrorValue( etype, value ) )
        except: entry['value'] = '<unprintable %s object>' % str( type(value).__name__ )

        entry['req_text'] = ''
        if REQUEST is not None:
            try: entry['req_text'] = REQUEST.text()
            except: pass

            try: entry['username'] = getToolByName( self, 'portal_membership' ).getMemberName( entry['userid'] )
            except: pass

            REQUEST.set( '_LastLogEntryId', entry['id'] )

        entry['version'] = Config.ProductVersion
        entry['zope_info'] = Config.ZopeInfo
        entry['python_info'] = Config.PythonInfo
        entry['system_info'] = Config.SystemInfo

        entry['comment'] = entry['comment_adm'] = ''

        # the transaction was aborted by exception handler,
        # thus we can (almost) safely commit our log entry
        for i in range(3):
            try:
                tts = transaction.get()
                if REQUEST is not None:
                    ob = REQUEST.get( 'PUBLISHED', self )
                    if hasattr(ob, '_p_changed'):
                        ob._p_changed = 0
                    Zope2.zpublisher_transactions_manager.recordMetaData( ob, REQUEST )
                else:
                    tts.note( self.physical_path() )
                tts.note( "logged exception" )
                tts.commit()
            except ConflictError:
                log.append( entry )
                continue
            except:
                LOG( 'ErrorLogTool.raising', ERROR,
                     "Cannot save error log entry [%s]:" % entry['id'], error=exc_info() )
            break

        return url

    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'getLogEntryById' )
    def getLogEntryById( self, id=None ):
        """
            Returns the specified log entry.

            Makes a copy to prevent changes. If log entry id is not specified,
            returns the last error entry for the current request.

            Arguments:

                'id' -- optional log entry id

            Result:

                The copy of the log entry or None if not found.
        """
        return self._getLogEntry( id )

    security.declarePublic( 'getLastEntryId' )
    def getLastEntryId( self, REQUEST=None ):
        """
            Returns id of the most recent log entry for the request.

            Arguments:

                'REQUEST' -- specifies Zope request object; if not given
                             the method will try to acquire it from context

            Result:

                The id of the log entry or None if not found.
        """
        REQUEST = REQUEST or aq_get( self, 'REQUEST', None )
        return REQUEST and REQUEST.get( '_LastLogEntryId' )

    security.declarePublic( 'getLogEntryAsText' )
    def getLogEntryAsText( self, id, REQUEST=None ):
        """
            Returns log entry formatted as plain text.

            Arguments:

                'id' -- log entry id

                'REQUEST' -- optional Zope request object; if present,
                             the method will set text/plain content type
                             in the response

            Result:

                Multiline text string describing error.
        """
        if REQUEST is not None:
            charset = REQUEST.get( 'LOCALIZER_CHARSET', '' )
            RESPONSE = REQUEST.RESPONSE
            RESPONSE.setHeader( 'content-type', 'text/plain; charset=%s' % charset )
        else:
            RESPONSE = None

        entry = self._getLogEntry( id, copy=0 )
        if entry is None:
            if RESPONSE is None:
                return None
            msg = getToolByName( self, 'msg', None )
            if msg is None:
                return
            return msg( "Log entry [%(id)s] not found or expired." ) % { 'id':id }

        return _entryTextTemplate % entry

    def _getLog( self ):
        """
            Returns the log entry container for this object.

            Result:

                The persistent list object containing log entries.
        """
        try:
            return self._log
        except AttributeError:
            return SiteErrorLog._getLog( self )

    def _getLogEntry( self, id=None, copy=1 ):
        """
            Returns the specified log entry or None.

            Used by public methods. Optionally makes a copy of the
            entry to prevent changes. If id is not specified,
            returns the last error entry for the current request.

            Arguments:

                'id' -- optional log entry id

            Result:

                The log entry or None if not found.
        """
        id = id or self.getLastEntryId()
        if not id:
            return None

        log = self._getLog()
        for entry in log:
            if entry['id'] == id:
                break
        else:
            return None

        # ordinary users are allowed to view only their own entries
        # XXX need to check context of the user
        user = getSecurityManager().getUser().getUserName()
        if user != entry['userid'] and not _checkPermission( Permissions.UseErrorLogging, self ):
            raise Unauthorized( id, entry )

        return copy and entry.copy() or entry

    security.declarePublic( 'sendErrorReport' )
    def sendErrorReport( self, id, comment='', admin=1, support=None, REQUEST=None ):
        """
            Sends error report to the administrator and support service by e-mail.

            Error reports can be sent only by the user who faced
            the error, or by the administrator. User's comment gets added
            to the error log entry.

            Either portal administrator (by default) or product support
            service or both may be specified as the recipients of the report.
            Administrator's e-mail address is taken from the portal
            configuration, whereas support e-mail is specified as the
            Config.ErrorReportAddress value.

            For the administrator notification 'error_notify_admin' mail
            template is used, which includes only user's comment and basic
            exception information, along with link to the error entry page.

            Support service receives full error report.

            Arguments:

                'id' -- log entry id

                'comment' -- optional user's comment on the error

                'admin' -- optional flag indicating whether to notify portal administrator

                'support' -- optional flag indicating whether to notify product support service

                'REQUEST' -- optional Zope request object

            Result:

                Redirect URL to the portal status page if the REQUEST
                is given.
        """
        try:
            entry = self._getLogEntry( id, copy=0 )
            if entry is None:
                # id is inserted to the redirect below
                raise SimpleError, "Log entry %(id)s not found or expired."

            comment = comment.strip()
            if entry['comment']:
                entry['comment_adm'] = comment
            else:
                entry['comment'] = comment
                entry['comment_adm'] = '\n'.join( [ '> ' + line for line in comment.split('\n') ] )

            #try:
            #    if support: # and _checkPermission( Permissions.UseErrorLogging, self ):
            #        support = Config.ErrorReportAddress
            #    else:
            #        support = None
            #    if admin or not support:
            #        admin = getToolByName( self, 'portal_properties' ).getProperty( 'email_from_address' )
            #except:

            prptool = getToolByName( self, 'portal_properties', None )
            if not prptool:
                raise SimpleError, "Can not get Portal Properties Tool."

            mail = getToolByName( self, 'MailHost' )
            if not prptool:
                raise SimpleError, "Can not get MailHost Tool."

            x = prptool.getProperty('email_error_address') or prptool.getProperty('email_from_address')
            email_admin = x and x.split(';') or None
            x = prptool.getProperty('send_to_support')
            email_support = x and Config.ErrorReportAddress or None

            if not ( email_admin or email_support ):
                raise SimpleError, "Administrative e-mail address is not set in the portal configuration."

            count = 0

            if admin and email_admin:
                count += mail.sendTemplate( 'error_notify_admin', email_admin, from_member=1, \
                                            id=id, comment=comment, entry=entry, raise_exc=1 )

            if support and email_support:
                # TODO: must have another mail template
                text = self.getLogEntryAsText( id )
                msg = mail.createMessage( 'text/plain' )
                msg['subject'] = 'Error report'
                msg.set_payload( comment + '\n' + text )
                count += mail.send( msg, [email_support], from_member=1, raise_exc=1 )

            if not count:
                raise SimpleError, "Delivery of the error report failed."

        except SimpleError, message:
            pass
        else:
            message = "Error report has been sent."

        if REQUEST is not None:
            return self.parent().redirect( action='status_page', message=message, params={ 'id':id }, REQUEST=REQUEST, )

    def _containment_onAdd( self, item, container ):
        # sets __error_log__ on the container
        SiteErrorLog.manage_afterAdd( self, item, container )

    def _containment_onDelete( self, item, container ):
        # unsets __error_log__ on the container
        SiteErrorLog.manage_beforeDelete( self, item, container )

InitializeClass( ErrorLogTool )


# template used by getLogEntryAsText

_entryTextTemplate = \
"""

SYSTEM INFORMATION

ExpressSuite Version:  %(version)s
Zope Version:    %(zope_info)s
Python Version:  %(python_info)s
System Platform: %(system_info)s

EXCEPTION INFORMATION

Error ID:        %(id)s
Time:            %(time_str)s
User Name:       %(userid)s (%(username)s)
Request URL:     %(url)s
Exception Type:  %(type)s
Exception Value: %(value)s

EXCEPTION TRACEBACK

%(tb_text)s

REQUEST

%(req_text)s
"""
