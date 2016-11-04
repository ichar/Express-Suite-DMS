""" 
Mail Folder classes
$Id: MailFolder.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 27/05/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from zLOG import LOG, INFO, TRACE, ERROR

from email.Utils import getaddresses
from poplib import error_proto
from re import sub, compile
from string import join
from types import ListType, TupleType
from urllib import quote
import sys

from Acquisition import aq_parent, aq_base, aq_get
from AccessControl import ClassSecurityInfo
from BTrees.OIBTree import OIBTree
from BTrees.OOBTree import OOSet
from DateTime import DateTime
from Globals import HTMLFile

from OFS.CopySupport import CopyError
from OFS.ObjectManager import ObjectManager
from ZODB.POSException import ConflictError, ReadConflictError
from whrandom import random

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.ActionInformation import ActionInformation
from Products.CMFCore.Expression import Expression
from Products.CMFCore.utils import getToolByName, _getAuthenticatedUser

import Config, Features
from Config import Roles, Permissions
from Heading import Heading, factory_type_information as Heading_fti
from HTMLDocument import HTMLDocument, factory_type_information as HTMLDocument_fti
from HTMLCleanup import HTMLCleaner
from Mail import MailMessage, MailFilter, getContentId, formataddr
from TemporalExpressions import UniformIntervalTE
from TransactionManager import BeginThread, CommitThread, UpdateRequestRuntime, interrupt_thread

from Utils import InitializeClass, cookId, joinpath, formatPlainText

from CustomDefinitions import CustomIncomingCategory

default_incoming_actions = ( \
              { 'id'          : 'view'
              , 'name'        : 'View'
              , 'action'      : 'folder'
              , 'permissions' : ( CMFCorePermissions.View, )
              , 'category'    : 'folder'
              },
              { 'id'          : 'edit'
              , 'name'        : 'Properties'
              , 'action'      : 'folder_edit_form'
              , 'permissions' : ( CMFCorePermissions.ChangePermissions, )
              , 'category'    : 'folder'
              },
              { 'id'          : 'filter'
              , 'name'        : 'Content filter'
              , 'action'      : 'portal_membership/processFilterActions?open_filter_form=1'
              , 'permissions' : ( CMFCorePermissions.View, )
              , 'category'    : 'folder'
              },
              { 'id'          : 'check'
              , 'title'       : 'Check mail'
             #, 'description' : 'Receive incoming mail now'
              , 'action'      : 'string:${object_url}/checkNewMail'
              , 'permissions' : ( Permissions.UseMailServerServices, )
              , 'category'    : 'folder'
              , 'condition'   : "python: object.mail_login"
              , 'visible'     : 1
              },
              { 'id'          : 'activate'
              , 'title'       : 'Activate mail'
             #, 'description' : 'Enable automatic mail check'
              , 'action'      : 'string:${object_url}/activate'
              , 'permissions' : ( Permissions.UseMailServerServices, )
              , 'category'    : 'folder'
              , 'condition'   : "python: not object.mail_enabled"
              , 'visible'     : 1
              },
              { 'id'          : 'deactivate'
              , 'title'       : 'Deactivate mail'
             #, 'description' : 'Disable automatic mail check'
              , 'action'      : 'string:${object_url}/deactivate'
              , 'permissions' : ( Permissions.UseMailServerServices, )
              , 'category'    : 'folder'
              , 'condition'   : "python: object.mail_enabled"
              , 'visible'     : 1
              },
        )

default_outgoing_actions = ( \
              { 'id'          : 'view'
              , 'name'        : 'View'
              , 'action'      : 'folder'
              , 'permissions' : ( CMFCorePermissions.View, )
              , 'category'    : 'folder'
              },
              { 'id'          : 'edit'
              , 'name'        : 'Properties'
              , 'action'      : 'folder_edit_form'
              , 'permissions' : ( CMFCorePermissions.ChangePermissions, )
              , 'category'    : 'folder'
              },
              { 'id'          : 'filter'
              , 'name'        : 'Content filter'
              , 'action'      : 'portal_membership/processFilterActions?open_filter_form=1'
              , 'permissions' : ( CMFCorePermissions.View, )
              , 'category'    : 'folder'
              },
              { 'id'          : 'send'
              , 'title'       : 'Send mail'
             #, 'description' : 'Send queued mail'
              , 'action'      : 'string:${object_url}/confirm_dispatch'
              , 'permissions' : ( Permissions.UseMailHostServices, )
              , 'category'    : 'folder'
              , 'condition'   : "python: object.mail_login"
              , 'visible'     : 1
              },
        )


factory_type_information = ( \
        { 'id'                      : 'Mail Folder'
        , 'title'                   : 'Mail Folder'
        , 'description'             : """E-mail folder"""
        , 'content_icon'            : 'folder_icon.gif'
        , 'sort_order'              : 0.3
        , 'product'                 : 'ExpressSuiteTools'
        , 'filter_content_types'    : 1
        , 'allowed_content_types'   : ( HTMLDocument_fti[0]['id'], )
        , 'immediate_view'          : 'folder_edit_form'
        , 'actions'                 : Heading_fti[0]['actions'][:]
        },

        { 'id'                      : 'Incoming Mail Folder'
        , 'content_meta_type'       : 'Incoming Mail Folder'
        , 'title'                   : 'Incoming Mail Folder'
        , 'description'             : """Incoming e-mail folder"""
        , 'type_group'              : 'Mail Folder'
        , 'factory'                 : 'addIncomingMailFolder'
        , 'permissions'             : ( Permissions.UseMailServerServices, )
        , 'actions'                 : default_incoming_actions[:]
        },

        { 'id'                      : 'Fax Incoming Folder'
        , 'content_meta_type'       : 'Fax Incoming Folder'
        , 'title'                   : 'Fax Incoming Folder'
        , 'description'             : """Fax Incoming Folder"""
        , 'type_group'              : 'Mail Folder'
        , 'factory'                 : 'addFaxIncomingFolder'
        , 'permissions'             : ( Permissions.UseMailServerServices, )
        , 'actions'                 : default_incoming_actions[:]
        },

        { 'id'                      : 'Outgoing Mail Folder'
        , 'content_meta_type'       : 'Outgoing Mail Folder'
        , 'title'                   : 'Outgoing Mail Folder'
        , 'description'             : """Outgoing e-mail folder"""
        , 'type_group'              : 'Mail Folder'
        , 'factory'                 : 'addOutgoingMailFolder'
        , 'permissions'             : ( Permissions.UseMailHostServices, )
        , 'actions'                 : default_outgoing_actions[:]
        },
    )


def addIncomingMailFolder( self, id, title='' ):
    """
        Add a new IncomingMailFolder object
    """
    self._setObject( id, IncomingMailFolder(id, title), set_owner=0 )

def addFaxIncomingFolder( self, id, title='' ):
    """
        Add a new FaxIncomingMailFolder object
    """
    self._setObject( id, FaxIncomingFolder(id, title), set_owner=0 )

def addOutgoingMailFolder( self, id, title='' ):
    """
        Add a new OutgoingMailFolder object
    """
    self._setObject( id, OutgoingMailFolder(id, title), set_owner=0 )


class MailFolderBase( Heading ):
    """
        Base Mail Folder class
    """
    _class_version = 1.0

    meta_type = None
    portal_type = None

    __implements__ = ( Features.isMailFolder,
                       Heading.__implements__,
                     )

    __unimplements__ = ( Features.canHaveSubfolders,
                       )

    security = ClassSecurityInfo()

    _properties = Heading._properties

    def hasMainPage( self ):
        """ Mail folder has no main page
        """
        return 0

    def getMainPage( self ):
        """ Mail folder has no main page
        """
        return None

InitializeClass( MailFolderBase )


class IncomingMailFolder( MailFolderBase ):
    """
        Incoming Mail Folder class
    """
    _class_version = 1.0

    meta_type = 'Incoming Mail Folder'
    portal_type = 'Incoming Mail Folder'

    __implements__ = ( Features.isIncomingMailFolder,
                       MailFolderBase.__implements__,
                     )

    __unimplements__ = ( Features.isContentStorage,
                       )

    security = ClassSecurityInfo()

    security.declareProtected( Permissions.UseMailServerServices, 'manage_addIncomingMailFolder')
    security.declareProtected( Permissions.UseMailServerServices, 'activate' )
    security.declareProtected( Permissions.UseMailServerServices, 'deactivate' )
    security.declareProtected( Permissions.UseMailServerServices, 'fetchMail' )
    security.declareProtected( CMFCorePermissions.ManageProperties, 'manage_changeProperties' )

    _properties = MailFolderBase._properties + (
            {'id':'mail_login',              'type':'string',        'mode':'w'},
            {'id':'mail_password',           'type':'string',        'mode':'w'},
            {'id':'mail_keep',               'type':'boolean',       'mode':'wd'},
            {'id':'mail_enabled',            'type':'boolean',       'mode':'w'},
            {'id':'mail_interval',           'type':'int',           'mode':'wd'},
        )

    # default attribute values
    mail_login = None
    mail_keep = 0
    mail_enabled = None
    mail_interval = Config.MailDefaultInterval
    mail_task = None

    def _initstate( self, mode ):
        """ Initialize attributes
        """
        if not MailFolderBase._initstate( self, mode ):
            return 0

        if getattr( self, 'mail_filter', None ) is None:
            self.mail_filter = MailFilter()

        if getattr( self, 'mail_seen', None ) is None:
            self.mail_seen = OIBTree()

        return 1

    def getServer( self ):
        """
            Returns the nearest mail server object.

            Result:

                'MailServerBase' object.
        """
        return getToolByName( self, 'MailServer', None )

    def activate( self, enable=1, REQUEST=None ):
        """ Enable automatic mail delivery
        """
        if not enable:
            return self.deactivate()

        server = self.getServer()
        if not server:
            raise Exceptions.SimpleError( 'mail.server_not_found' )

        scheduler = getToolByName( self, 'portal_scheduler', None )
        if scheduler:
            se = self.mail_task and scheduler.getScheduleElement( self.mail_task )
            if se is not None:
                se.resume()
            else:
                title = '%s://%s@%s' % ( server.protocol.lower(), self.mail_login, server.address() )
                temporal_expr = UniformIntervalTE( seconds=(self.mail_interval * 60) )
                self.mail_task = scheduler.addScheduleElement( self.fetchMail, temporal_expr=temporal_expr, title=title )

        self.mail_enabled = True

        if REQUEST is not None:
            status = 'New mail will be checked automatically.'
            return REQUEST.RESPONSE.redirect( self.absolute_url( message=status ), status=303 )

    def deactivate( self, remove=0, REQUEST=None ):
        """ Disable automatic mail retrieval
        """
        scheduler = getToolByName( self, 'portal_scheduler', None )
        task = self.mail_task

        if scheduler and task:
            se = scheduler.getScheduleElement( task )
            if se is not None:
                if remove:
                    se.suspend()
                else:
                    scheduler.delScheduleElement( task )

        self.mail_enabled = False

        if REQUEST is not None:
            status = 'Mail will not be checked.'
            return REQUEST.RESPONSE.redirect( self.absolute_url( message=status ), status=303 )

    def setMailAccount( self, login=None, password=None ):
        """ Change mail account name and password
        """
        if login is not None:
            login = str(login).strip()

            server = getToolByName( self, 'MailServer', None )
            if server:
                # TODO: reformat possible exception
                server.replace_account( self.mail_login, login, self )

            if self.mail_enabled and not login:
                self.deactivate()

            self.mail_login = login

        if password is not None:
            self.mail_password = str( password )

    def keepMessages( self, value ):
        """ Configure whether seen messages are deleted from the server
        """
        self.mail_keep = int( value )

    def setInterval( self, value ):
        """ Change automatic mail check interval
        """
        value = int( value )
        server = getToolByName( self, 'MailServer', None )

        if server and server.min_interval is not None:
            if value < server.min_interval:
                value = server.min_interval

        self.mail_interval = value

        # update task frequency to the new interval
        scheduler = getToolByName( self, 'portal_scheduler', None )
        if scheduler and self.mail_task:
            se = scheduler.getScheduleElement( self.mail_task )
            if se is None:
                return
            interval = value * 60
            temporal_expr = UniformIntervalTE( seconds=interval )
            se.setTemporalExpression( temporal_expr )

    def getAllowedSenders( self ):
        """ Get list of accepted sender e-mail addresses
        """
        return self.mail_filter.get( 'senders' ) or []

    def setAllowedSenders( self, *values, **args ):
        """ Set list of accepted sender e-mail addresses
        """
        self.mail_filter.reset()
        senders = args['list'] # TODO
        if senders:
            self.mail_filter.add( 'sender', id='senders', list=senders )

    def checkNewMail( self, REQUEST=None ):
        """ Check new mail from the server (action)
        """
        self.fetchMail( REQUEST, force=1 )

    def fetchMail( self, REQUEST=None, force=None ):
        """ Fetch new mail from the server
        """
        IsRun = 1

        if not force and getattr( self, 'activate_timestamp', None ):
            start_time_hour = getattr( self, 'start_time_hour', 8 )
            start_time_minute = getattr( self, 'start_time_minute', 45 )
            finish_time_hour = getattr( self, 'finish_time_hour', 18 )
            finish_time_minute = getattr( self, 'finish_time_minute', 15 )
            scheduler_workday_only = getattr( self, 'scheduler_workday_only', 1 )

            today = DateTime()
            yy, mon, day, h, m, s, tz = today.parts()

            if h < start_time_hour or ( h == start_time_hour and m < start_time_minute ):
                IsRun = 0
            elif h > finish_time_hour or ( h == finish_time_hour and m > finish_time_minute ):
                IsRun = 0
            elif scheduler_workday_only and today.pDay()[:3].lower() in ['sat','sun']:
                IsRun = 0

        if IsRun:
            action = 'IncomingMailFolder.fetchMail'
            server = getToolByName( self, 'MailServer' )

            LOG(action, INFO, "BEGIN: %s, server: %s" % ( self.id, server ) )

            try: uname = _getAuthenticatedUser(self).getUserName()
            except: uname = 'System Processes'

            editors = self.editor()
            if editors:
                membership = getToolByName( self, 'portal_membership', None )
                editor = membership is not None and membership.getMemberById( editors[0] ) or None
            else:
                editor = None

            try:
                server.open( self.mail_login, self.mail_password )
            except error_proto:
                if REQUEST:
                    message = 'Incorrect login or password'
                    return REQUEST.RESPONSE.redirect( self.absolute_url( action='view', message=message ) )

            server.folder( Config.MailInboxName, seen=self.mail_seen )
            if not self.mail_keep:
                server.delete( old=1 )

            LOG(action, INFO, "connected by: editor %s, mail_keep %s" % ( editor, self.mail_keep ) )

            count = 0
            IsTryToFetch = -1
            IsError = 0
            docs = []

            for msg in server.fetch( mark=0 ):
                BeginThread( self, action, force=1 )
                IsError = 0

                doc_ob = self.documentFromMail( msg )
                doc_id = doc_ob.getId()

                if not doc_id in docs:
                    docs.append( doc_id )
                    IsTryToFetch = 0
                elif IsTryToFetch:
                    break
                else:
                    IsTryToFetch = 1
                    continue

                try:
                    self._setObject( doc_id, doc_ob, set_owner=0 )
                    doc = self._getOb( doc_id )

                    # set ownership
                    if editor:
                        doc.changeOwnership( editor.getUser() )
                    # make initial workflow state
                    if hasattr(aq_base(doc), 'notifyWorkflowCreated'):
                        doc.notifyWorkflowCreated()

                    self.mail_seen[ msg.uid ] = 1

                except ( ConflictError, ReadConflictError ):
                    server.close()
                    raise
                except:
                    LOG(action, ERROR, "Error", error=sys.exc_info())
                    IsError = 1

                if not CommitThread( self, action, IsError, force=1, subtransaction=None ):
                    IsError = 1

                if IsError: continue

                count += 1
                LOG(action, INFO, "Added document: doc_id %s, uid %s, count %s, msg.uid %s" % ( \
                    doc_id, doc.getUid(), count, msg.uid ) )

                # send Notification to editor
                try:
                    self.sendNotification( doc )
                except AttributeError:
                    pass

                # delete from source
                if not self.mail_keep:
                    server.delete( msg.uid )

                # Publish if needed
                try: self.announce_publication( doc_id )
                except: pass

            server.close()
            LOG(action, INFO, "END: IsError %s, IsTryToFetch %s, count %s]" % ( IsError, IsTryToFetch, count ) )

        if REQUEST is not None:
            if IsTryToFetch:
                status = count and 'Received new messages. But identification error was detected!' or 'No new mail.'
            else:
                status = count and 'Received new messages.' or 'No new mail.'

            return REQUEST.RESPONSE.redirect(
                    self.absolute_url( action='folder', message=status ),
                    status=303 )

    def documentFromMail( self, msg, factory=HTMLDocument ):
        """
            Convert MailMessage object to a new document item
        """
        name = email = ''

        for header in ( 'from', 'reply-to', 'sender' ):
            parsed = getaddresses( msg.get_all( header, decode=1 ) )
            if parsed:
                name, email = parsed[ 0 ]
                break

        subject = msg.get( 'subject', '', decode=1 )
        text = content = None

        doc = factory( cookId( self, msg.uid ), title=subject, text_format='plain' )
        aq_doc = doc.__of__( self )

        date = msg.get( 'date', '', decode=1 )
        # workaround for the DateTime bugs
        date = sub( r'\s+([+-]\d{4})(?:\s+\(?[A-Za-z]+\)?)?\s*\Z', r' GMT\1', date, 1 )
        try:
            date = DateTime( date )
            date = date.toZone( date.localZone() )
        except:
            date = DateTime()
        doc.setEffectiveDate( date )

        aq_doc.setCategory( 'IncomingMail' )
        aq_doc.setCategoryAttribute( 'senderName', name, reindex=0 )
        aq_doc.setCategoryAttribute( 'senderAddress', email, reindex=0 )
        aq_doc.setCategoryAttribute( 'isValidSender', self.mail_filter.match( msg ), reindex=0 )

        for part in msg.walk():
            if part.is_multipart():
                continue
            try:
                data = part.get_payload( decode=1 )
                ctype = part.get_content_type()
            except:
                data = part.get_payload()
                ctype = Config.DefaultAttachmentType

            if text is None and ctype in doc.allowed_content_types:
                # TODO: support for multipart/alternative, multipart/related
                text = part
                content = data
                #LOG( 'MailFolder.documentFromMail', TRACE, 'text = %s' % content )

            else:
                fname = part.get_filename( decode=1 )
                aq_doc.addFile( file=data, title=fname, content_type=ctype, unresticted=1 )
                #LOG( 'MailFolder.documentFromMail', TRACE, 'attached %s = %s' % (ctype, fname) )

        if text is not None:
            if content is None:
                # must not be reached
                content = text.get_payload( decode=1 )

            subtype = text.get_content_subtype()
            if subtype == 'html':
                # TODO: need better cleaner
                content = HTMLCleaner( content, None, 0, '', 'HEAD SCRIPT STYLE' )

            elif subtype == 'plain':
                content = formatPlainText( content, target='_blank' )
                subtype = 'html'

            doc.setFormat( subtype )
            doc._edit( content )

            lang = text.get( 'content-language', '', decode=1 )
            lang = lang.replace( ',', ' ' ).split()
            if lang:
                doc.setLanguage( lang[0] )

        return doc

    def manage_addIncomingMailFolder( self, id, title='', REQUEST=None ):
        """
            Add a new IncomingMailFolder object
        """
        addIncomingMailFolder( self, id, title )
        item = self._getOb( id )

        if None not in ( item, REQUEST ):
            return REQUEST.RESPONSE.redirect(
                    item.absolute_url( action='folder_edit_form', message='Incoming e-mail folder added.' ),
                    status=303 )

    def manage_afterAdd( self, item, container ):
        """ Actions to be executed after the object is created
        """
        MailFolderBase.manage_afterAdd( self, item, container )

        membership = getToolByName( self, 'portal_membership' )
        member = membership.getAuthenticatedMember()
        addr   = member.getMemberEmail() or member.getUserName()
        login  = addr.split( '@', 1 )[0]
        scheduler = getToolByName( self, 'portal_scheduler', None )
        # update object path in the scheduler's task
        task = self.mail_task
        if scheduler and task:
            se = scheduler.getScheduleElement( task )
            if se is not None:
                path = self.physical_path()
                # XXX refresh scheduler's queue
                se.target_path = path

        server = getToolByName( self, 'MailServer', None )
        if server:
            if server.has_account( login ):
                login = ''
            if server.min_interval is not None:
                self.setInterval( server.min_interval )

        self.setMailAccount( login, '' )

    def manage_beforeDelete( self, item, container ):
        """ Actions to be executed before the object is deleted
        """
        self.deactivate( 1 )

        if self.mail_login:
            server = getToolByName( self, 'MailServer', None )
            if server:
                try: server.unregister_account( self.mail_login, self )
                except KeyError: pass

        MailFolderBase.manage_beforeDelete( self, item, container )

    def manage_changeProperties( self, REQUEST=None, **kw ):
        """ Change existing object properties
        """
        login, password, enabled, interval, senders = \
                self._extract( REQUEST, kw, 'mail_login', 'mail_password',
                                            'mail_enabled', 'mail_interval',
                                            'mail_senders' )

        if login is not None:
            self.setMailAccount( login, password )
        if interval is not None:
            self.setInterval( interval )
        if senders is not None:
            self.setAllowedSenders( list=senders )

        res = MailFolderBase.manage_changeProperties( self, REQUEST and {}, **kw )

        if enabled is None and self.mail_enabled is None and self.mail_login:
            enabled = 1

        if enabled is not None:
            self.activate( enabled )

        return res

    def _getCopy( self, container ):
        """ Copy operation support
        """
        new = MailFolderBase._getCopy( self, container )

        new.setMailAccount( '', '' )

        new.mail_enabled  = 0
        new.mail_task     = None

        return new

    def _notifyOfCopyTo( self, container, op=0 ):
        """ Move operation support
        """
        MailFolderBase._notifyOfCopyTo( self, container, op )

        # 1 is move op
        if op != 1 or self.mail_task is None:
            return

        new_self = aq_base( self ).__of__( container )

#
# Not needed with current mail server implementation
#
#       TODO: this assumes single mail server
#       server = getToolByName( self, 'MailServer', None )
#       if server:
#           server.replace_account( self.mail_login, self.mail_login, new_self, force=1 )

        if self.mail_task is not None:
            planner = getToolByName( self, 'portal_scheduler', None )
            element = planner and planner.getScheduleElement( self.mail_task )
            if planner and element:
                new_path = new_self.physical_path()
                element.target_path = new_path

    def filtered_meta_types( self, user=None ):
        """ Disallow interactive item creation
        """
        return ()

    def cb_dataValid( self ):
        """ Disallow paste into self
        """
        return 0

    def _verifyObjectPaste( self, object, validate_src=1 ):
        """ Disallow paste into self
        """
        return #raise CopyError # TODO

InitializeClass( IncomingMailFolder )


class FaxIncomingFolder( IncomingMailFolder ):
    """
        Fax Incoming Folder class
    """
    _class_version = 1.0

    meta_type = 'Fax Incoming Folder'
    portal_type = 'Fax Incoming Folder'

    __implements__ = ( Features.isIncomingMailFolder,
                       MailFolderBase.__implements__,
                     )

    __unimplements__ = ( Features.isContentStorage,
                       )

    security = ClassSecurityInfo()

    security.declareProtected( CMFCorePermissions.ManageProperties, 'manage_changeProperties' )

    _properties = IncomingMailFolder._properties + (
            {'id':'start_time_hour',         'type':'int',           'mode':'w'},
            {'id':'start_time_minute',       'type':'int',           'mode':'w'},
            {'id':'finish_time_hour',        'type':'int',           'mode':'w'},
            {'id':'finish_time_minute',      'type':'int',           'mode':'w'},
            {'id':'scheduler_workday_only',  'type':'int',           'mode':'w'},
            {'id':'activate_timestamp',      'type':'int',           'mode':'w'},
        )

    start_time_hour = 8
    start_time_minute = 45
    finish_time_hour = 18
    finish_time_minute = 15
    scheduler_workday_only = 1
    activate_timestamp = 0
    mail_interval = 15

    def manage_changeProperties( self, REQUEST=None, **kw ):
        """
            Changes existing object properties
        """
        uname = _getAuthenticatedUser(self).getUserName()

        start_time_h, start_time_m, finish_time_h, finish_time_m, scheduler_workday_o, activate_timestamp = \
                self._extract( REQUEST, kw, 'start_time_hour', 'start_time_minute', \
                                            'finish_time_hour', 'finish_time_minute', \
                                            'scheduler_workday_only', 'activate_timestamp' )

        #check time range
        if 0 <= start_time_h <= 23:
            self.start_time_hour = start_time_h
        if 0 <= start_time_m <= 59:
            self.start_time_minute = start_time_m
        if 0 <= finish_time_h <= 23:
            self.finish_time_hour = finish_time_h
        if 0 <= finish_time_m <= 59:
            self.finish_time_minute = finish_time_m

        changed = 'INCOMING [start %s:%s, finish %s:%s]' % ( self.start_time_hour, self.start_time_minute, \
            self.finish_time_hour, self.finish_time_minute )

        self.scheduler_workday_only = scheduler_workday_o and 1 or 0
        self.activate_timestamp = activate_timestamp and 1 or 0

        LOG('MailFolder.FaxIncomingFolder', INFO, 'properties changed by %s' % uname, '%s, workdays %s, active %s\n' % ( \
            changed, self.scheduler_workday_only, self.activate_timestamp ))

        res = IncomingMailFolder.manage_changeProperties( self, REQUEST and {}, **kw )

        return res

    def documentFromMail( self, msg, factory=HTMLDocument ):
        """
            Convert MailMessage object to a new document item
        """
        name = email = ''

        subject = msg.get( 'subject', '', decode=1 )
        text = content = None

        id = cookId( self, msg.uid )
        doc = factory( id, title=subject, text_format='plain' )

        aq_doc = doc.__of__( self )

        date = msg.get( 'date', '', decode=1 )
        # workaround for the DateTime bugs
        date = sub( r'\s+([+-]\d{4})(?:\s+\(?[A-Za-z]+\)?)?\s*\Z', r' GMT\1', date, 1 )
        try:
            date = DateTime( date )
            date = date.toZone( date.localZone() )
        except:
            date = DateTime()
        doc.setEffectiveDate( date )

        aq_doc.setCategory( CustomIncomingCategory() )
        category = aq_doc.getCategory()
        if category is None:
            return None

        #set attributes values selected by default
        for attr in category.listAttributeDefinitions():
            if attr is None:
                continue
            attr_type = attr.Type()
            if attr.haveComputedDefault():
                if attr_type == 'userlist':
                    aq_doc.setCategoryAttribute( attr.getId(), self.Creator(), reindex=0 )
                elif attr_type == 'date':
                    aq_doc.setCategoryAttribute( attr.getId(), date, reindex=0 )
                elif attr_type == 'lines':
                    member = None
                    try:
                        member = self.portal_membership.getMemberById( self.Creator() )
                    except KeyError:
                        pass
                    if member is not None:
                        department = member.getMemberDepartment()
                        if department in attr.getDefaultValue():
                            aq_doc.setCategoryAttribute( attr.getId(), department, reindex=0 )
            elif attr_type != 'lines':
                aq_doc.setCategoryAttribute( attr.getId(), attr.getDefaultValue(), reindex=0 )

        for part in msg.walk():
            if part.is_multipart():
                continue
            try:
                data = part.get_payload( decode=1 )
                ctype = part.get_content_type()
            except:
                data = part.get_payload()
                ctype = Config.DefaultAttachmentType

            if text is None and ctype in doc.allowed_content_types:
                # TODO: support for multipart/alternative, multipart/related
                text = part
                content = data
            else:
                fname = part.get_filename( decode=1 )
                if not fname or fname.startswith('file'):
                    LOG( 'MailFolder.documentFromMail', INFO, 'file ignored: %s' % fname )
                    continue
                try:
                    aq_doc.addFile( file=data, title=fname, content_type=ctype, unresticted=1 )
                except: pass

        if text is not None:
            if content is None:
                # must not be reached
                content = text.get_payload( decode=1 )

            subtype = 'html'
            doc.setFormat( subtype )
            content = self.checkContent( content )

            aq_doc.setCategoryAttribute( 'IN_Rep', content, reindex=0 )

            lang = text.get( 'content-language', '', decode=1 )
            lang = lang.replace( ',', ' ' ).split()
            if lang:
                doc.setLanguage( lang[0] )

        category.applyDocumentTemplate( aq_doc )

        return doc

    def checkContent( self, content=None ):
        if not content:
            return ''

        i = 3
        n = 0
        while i > 0:
            i -= 1
            n = content.find('***'+'\n', n+1)

        if n > 1:
            content = content[0:n+3]

        return content

    def sendNotification( self, doc ):
        # send notifications that new fax was received
        mail = getToolByName( self, 'MailHost' )
        if not mail:
            return

        #doc_url = doc.absolute_url( action='document_attaches', frame='document_frame', canonical=1 )
        doc_url = doc.absolute_url( canonical=1 )
        doc_url = "%s/document_frame?link=document_attaches" % doc_url
        report = doc.getCategoryAttribute( 'IN_Rep' )
        kwargs = {}
        kwargs.setdefault( 'source_link', doc_url )
        kwargs.setdefault( 'fax_report', report )

        editors = self.editor()
        #writers = getToolByName(self, 'portal_membership').listAllowedUsers( self, [Config.WriterRole] )

        template = 'send_fax_notification'
        # mail.sendTemplate( template, editors + writers, raise_exc=0, **kwargs )
        mail.sendTemplate( template, editors, raise_exc=0, IsAntiSpam=0, **kwargs )

    def manage_addFaxIncomingFolder( self, id, title='', REQUEST=None ):
        """
            Add a new FaxIncomingMailFolder object
        """
        addFaxIncomingFolder( self, id, title )
        item = self._getOb( id )

        if None not in ( item, REQUEST ):
            return REQUEST.RESPONSE.redirect(
                    item.absolute_url( action='folder_edit_form', message='Fax Incoming Folder added.' ),
                    status=303 )

InitializeClass( FaxIncomingFolder )


class OutgoingMailFolder( MailFolderBase ):
    """
        Outgoing Mail Folder class
    """
    _class_version = 1.0

    meta_type = 'Outgoing Mail Folder'
    portal_type = 'Outgoing Mail Folder'

    __implements__ = ( Features.isOutgoingMailFolder,
                       MailFolderBase.__implements__,
                     )

    security = ClassSecurityInfo()

    security.declareProtected( Permissions.UseMailHostServices, 'manage_addOutgoingMailFolder')
    security.declareProtected( Permissions.UseMailHostServices, 'sendMail' )
    security.declareProtected( Permissions.UseMailHostServices, 'listQueued' )
    security.declareProtected( CMFCorePermissions.ManageProperties, 'manage_changeProperties' )

    mail_notify = HTMLFile( 'skins/mail_templates/mail_notify', globals() )

    _properties = MailFolderBase._properties + (
            {'id':'mail_from_name',	'type':'string',	'mode':'w'},
            {'id':'mail_from_address',	'type':'string',	'mode':'w'},
        )

    # default attribute values
    mail_from_name    = None
    mail_from_address = None

    def _initstate( self, mode ):
        """ Initialize attributes
        """
        if not MailFolderBase._initstate( self, mode ):
            return 0

        if getattr( self, 'mail_recipients', None ) is None:
            self.mail_recipients = OOSet()

        return 1

    def setFromAddress( self, email=None, name=None ):
        """ Set e-mail address for the From header
        """
        if name is not None:
            self.mail_from_name = str(name).strip()

        if email is not None:
            email = str(email).strip()

            server = getToolByName( self, 'MailHost', None )
            if server:
                # TODO: reformat possible exception
                server.replace_account( self.mail_from_address, email, self )

            self.mail_from_address = email

    def getRecipients( self ):
        """ Get list of recipients e-mail addresses
        """
        return self.mail_recipients

    def setRecipients( self, *values, **args ):
        """ Set list of recipients e-mail addresses
        """
        self.mail_recipients.clear()
        recipients = args['list'] # TODO
        if recipients:
            self.mail_recipients.update( recipients )

    def sendMail( self, ids=None, REQUEST=None ):
        """ Send mail messages through the smtp server
        """
        server = getToolByName( self, 'MailHost' )
        membership = getToolByName( self, 'portal_membership' )
        wftool = getToolByName( self, 'portal_workflow' )

        # TODO: must use language from user prefs
        try:
            lang = self.msg.get_selected_language()
        except AttributeError:
            lang = self.msg.get_default_language()

        internal_emails = []
        external_emails = []

        for addr in self.mail_recipients:
            member = addr.find('@') < 0 and membership.getMemberById( addr ) or None
            if member:
                internal_emails.append( member )
            else:
                external_emails.append( addr )

        if type(ids) is ListType or type(ids) is TupleType:
            docs = map( lambda id, self=self: self._getOb( id ), ids )
        else:
            docs = self.objectValues()

        queue = []
        count = 0
        mfrom = self.mail_from_address
        fax_number_re = compile( '[\d\-]+$' )

        for doc in docs:
            if not doc.isInCategory( 'OutgoingMail' ):
                continue
            if wftool.getInfoFor( doc, 'state' ) != 'queued':
                try: wftool.doActionFor( doc, 'dispatch', send=0 )
                except: continue
            queue.append( doc )

        server.open()

        for doc in queue:
            try:
                wftool.doActionFor( doc, 'deliver' )
            except:
                continue

            internal = []
            external = []
            fax = []

            rcpts = doc.getCategoryAttribute( 'recipientAddress' )
            #names = doc.getCategoryAttribute( 'recipientName' ) TODO: set To header

            if rcpts:
                for addr in rcpts.replace( ',', ' ' ).split():
                    member = addr.find('@') < 0 and membership.getMemberById( addr ) or None
                    if member:
                        internal.append( member )
                    elif fax_number_re.match( addr ):
                        fax.append( "%s@faxmaker.com" % addr )
                    else:
                        external.append( addr )

            if not (internal or external or fax):
                if not (internal_emails or external_emails):
                    try:
                        wftool.doActionFor( doc, 'fail', comment='No recipients specified.' )
                    except:
                        pass
                    continue

                internal = internal_emails
                external = external_emails

            res = 0

            if internal:
                text = self.mail_notify( doc, REQUEST, message=doc, parent=self, lang=lang )
                msg = server.createMessage( source=text )
                self.formatFromAddress( doc, msg )
                res += server.send( msg, internal, mfrom )

            if external:
                msg = self.mailFromDocument( doc, factory=server.createMessage )
                res += server.send( msg, external, mfrom )

            if fax:
                msg = self.mailFromDocument( doc, fax=True, factory=server.createMessage )
                res += server.send( msg, fax, mfrom )

            try:
                wftool.doActionFor( doc, res and 'fix' or 'fail' )
            except:
                pass

            count += res and 1

        server.close()

        if REQUEST is not None:
            if count == len(queue):
                status = count and 'Messages have been sent.' or 'Nothing to send.'
            elif queue:
                status = 'Some messages were not sent due to errors.'
            else:
                status = 'Nothing was sent due to errors.'

            return REQUEST.RESPONSE.redirect(
                    self.absolute_url( action='folder', message=status ),
                    status=303 )

    def mailFromDocument( self, doc, fax=False, factory=MailMessage, **headers ):
        """ Convert document item to a new MailMessage object
        """
        fmt = doc.Format()
        files = doc.listAttachments()
        msg = factory( fmt, multipart=len(files) and 'related' )
        body = msg.get_body()

        self.formatFromAddress( doc, msg )
        msg.set_header( 'subject', doc.Title() )

        for name, value in headers.items():
            msg.set_header( name, value )

        # TODO set document charset
        text = doc.FormattedBody( html=False, width=76, canonical=True )
        body.set_payload( text )

        # XXX fix url tool (and portal and site objects) to use server_url
        REQUEST = aq_get( self, 'REQUEST', None )
        if REQUEST is not None:
            urltool = getToolByName( self, 'portal_url' )
            portal_url = urltool()
        else:
            portal_url = aq_get( self, 'server_url', None, 1 )

        content_id = getContentId( doc, extra=1 )

        envelope = factory( multipart=1 )
        mht = factory( 'message/rfc822' )

        for id, file in files:
            ctype = file.getContentType()
            item = factory( ctype or Config.DefaultAttachmentType )
            cid = content_id % id
            inline = bool( text.count( cid ) )
            fname = file.getProperty('filename') or file.getId()

            if not fax or inline:
                t = msg
            else:
                # This will allow fax server to print attaches as well as the document text
                t = envelope 
            t.attach( item, inline=inline, filename=fname, cid=cid )
            item.set_payload( file.RawBody() )

        mht.attach( msg )
        envelope.attach( mht, filename='message.mht' )

        return envelope

    def formatFromAddress( self, doc=None, message=None ):
        """ Set From header from either folder properties or document owner
        """
        name = self.mail_from_name
        email = self.mail_from_address

        if not (name and email) and doc:
            membership = getToolByName( self, 'portal_membership' )
            owner = doc.getOwner( 1 )
            if owner and owner[1]:
                owner = membership.getMemberById( owner[1] )
            if owner:
                name = name  or owner.getMemberName()
                email = email or owner.getMemberEmail()

        if not email:
            return None

        if message:
            return message.set_header( 'from', (name, email) )

        # XXX set charset
        return formataddr( (name, email) )

    def listQueued( self, ids=None ):
        """ Search catalog for queued messages
        """
        catalog = getToolByName( self, 'portal_catalog' )
        states = ids and ( 'evolutive', 'pending', 'queued', 'failed' ) or ( 'queued', )
        query = {
                'parent_path' : self.physical_path(),
                'category' : 'OutgoingMail',
                'state' : states,
                }

        if type(ids) is ListType and ids:
            query['id'] = ids

        return catalog.searchResults( **query )

    def manage_addOutgoingMailFolder( self, id, title='', REQUEST=None ):
        """
            Add a new IncomingMailFolder object
        """
        addOutgoingMailFolder( self, id, title )
        item = self._getOb( id )

        if None not in ( item, REQUEST ):
            return REQUEST.RESPONSE.redirect(
                    item.absolute_url( action='folder_edit_form', message='Outgoing e-mail folder added.' ),
                    status=303 )

    def manage_afterAdd( self, item, container ):
        """ Actions to be executed after the object is created
        """
        MailFolderBase.manage_afterAdd( self, item, container )

        membership = getToolByName( self, 'portal_membership' )
        member = membership.getAuthenticatedMember()
        email = member.getMemberEmail()

        server = getToolByName( self, 'MailHost', None )
        if server and server.has_account( email ):
            email = ''

        self.setFromAddress( email, member.getMemberName() )

    def manage_beforeDelete( self, item, container ):
        """ Actions to be executed before the object is deleted
        """
        if self.mail_from_address:
            server = getToolByName( self, 'MailHost', None )
            if server:
                try: server.unregister_account( self.mail_from_address, self )
                except KeyError: pass

        MailFolderBase.manage_beforeDelete( self, item, container )

    def manage_changeProperties( self, REQUEST=None, **kw ):
        """ Change existing object properties
        """
        from_name, from_addr, recipients = \
                self._extract( REQUEST, kw, 'mail_from_name', 'mail_from_address', 'mail_recipients' )

        if not (from_name is None and from_addr is None):
            self.setFromAddress( from_addr, from_name )
        if recipients is not None:
            self.setRecipients( list=recipients )

        return MailFolderBase.manage_changeProperties( self, REQUEST and {}, **kw )

    def _getCopy( self, container ):
        """ Copy operation support
        """
        new = MailFolderBase._getCopy( self, container )

        new.setFromAddress( '' )

        return new

InitializeClass( OutgoingMailFolder )
