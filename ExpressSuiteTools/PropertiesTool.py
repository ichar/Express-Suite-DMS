"""
Portal Properties tool
$Id: PropertiesTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 20/11/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re
from AccessControl import ClassSecurityInfo

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.ActionInformation import ActionInformation
from Products.CMFCore.Expression import Expression
from Products.CMFCore.utils import getToolByName
from Products.CMFDefault.PropertiesTool import PropertiesTool as _PropertiesTool

import Config
import BackupFSRoot
from SimpleObjects import ToolBase

from Utils import InitializeClass, getLanguageInfo, addQueryString

from CustomDefinitions import portalConfiguration
from CustomObjects import ResolutionBackgroundColor


class PropertiesTool( ToolBase, _PropertiesTool ):
    """
        Portal properties tool
    """
    _class_version = 1.0

    meta_type = 'ExpressSuite Properties Tool'

    security = ClassSecurityInfo()

    manage_options = _PropertiesTool.manage_options # + ToolBase.manage_options

    _actions = _PropertiesTool._actions + (
                ActionInformation( \
                          id='configBackupFSRoot'
                        , title='Configure pack and backup options'
                        , description='Configure pack and backup options of the BackupFSRoot'
                        , action=Expression( text='string: ${portal_url}/backup_config_form' )
                        , permissions=( CMFCorePermissions.ManagePortal, )
                        , category='global'
                        , condition=None
                        , visible=1
                        ),
         )

    # restore method overridden by PropertyManager in ItemBase
    title = _PropertiesTool.title

    ### Override 'portal_properties' interface methods ###

    security.declareProtected( CMFCorePermissions.ManagePortal, 'editProperties' )
    def editProperties( self, props ):
        """
            Change portal settings
        """
        if props.has_key('backup_or_pack_only'):
            backupFSRoot = self._getBackupFSRoot()
            if backupFSRoot is not None:
                return backupFSRoot.editProperties( self.parent().absolute_url(1), props )
            return None

        portal = self.parent()
        portal.manage_changeProperties( props )
        
        lang = props.get('language')
        if lang:
            langinfo = getLanguageInfo( lang )
            portal.msg.manage_changeDefaultLang( lang )

            default_encoding = langinfo['python_charset']
            #catalog = getToolByName( self, 'portal_catalog' )
            #for idx in catalog.getIndexObjects():
            #    if idx.meta_type == 'TextIndexNG2':
            #        idx.default_encoding = default_encoding
        
        if props.has_key('smtp_server'):
            self.MailHost.address( props['smtp_server'] )
        
        if props.has_key('smtp_login'):
            login = props['smtp_login'] or None
            self.MailHost.setCredentials( login=login )

            password = login and props.get('smtp_password', '')
            if not password or len(password.replace('*', '')):
                self.MailHost.setCredentials( password=password )

        if props.has_key('mail_server'):
            self.MailServer.address( props['mail_server'] )

    def smtp_server( self ):
        """
            Returns smtp server address
        """
        return self.MailHost.address()

    def smtp_login( self ):
        """
            Returns smtp server login
        """
        return self.MailHost.login()

    def smtp_password( self ):
        """
            Returns smtp password
        """
        return self.MailHost.password()

    ### New interface methods ###

    security.declareProtected( CMFCorePermissions.AccessContentsInformation, 'getProperty' )
    def getProperty( self, id, default=None ):
        """
            Returns the portal property 'id', returning the optional second
            argument or None if no such property is found.
        """
        return self.parent().getProperty(id, default)

    def instance_name( self ):
        """
            Returns product instance name
        """
        return self.parent().getProperty('instance', 'docs')

    def remote_url( self, object_url='', params=None, validate=None ):
        """
            Returns archive storage url
        """
        remote_url = self.parent().getProperty('remote_url', None)
        server_url = self.parent().getProperty('server_url', None)
        if object_url and object_url.startswith('/arc'):
            url = '%s%s' % ( server_url, object_url )
        else:
            url = '%s%s' % ( remote_url, object_url or '' )
        if validate:
            r_instance = re.compile(r'(\:[\d]+)?\/(\w+)(/[storage|portal_links][/?&=#$A-Za-z0-9._\-+%]*)')
            try:
                m = r_instance.search(url)
                x = portalConfiguration.getAttribute('URLs', context=self, instance=m.group(2))
                if x:
                    url = x + m.group(3)
            except: pass
        if params:
            url = addQueryString( url, params )
        return url

    def common_url( self, object_url='', params=None ):
        """
            Returns common server url
        """
        common_url = self.parent().getProperty('common_url', None)
        if not common_url:
            urltool = getToolByName(self, 'portal_url', None)
            common_url = urltool()
        url = '%s%s' % ( common_url, object_url or '' )
        if params:
            url = addQueryString( url, params )
        return url

    def storage_type( self ):
        """
            Returns storage type: archive/storage
        """
        x = self.instance_name()
        try: instances = portalConfiguration.getAttribute('instances')
        except: instances = None
        if not x:
            type = 'unrestricted'
        elif x.startswith('arc'):
            type = 'archive'
        elif not instances or x in instances:
            type = 'storage'
        else:
            type = 'unrestricted'
        return type

    def getResolutionBackgroundColor( self ):
        return ResolutionBackgroundColor()

    def task_finalize_settings( self, id=None ):
        """
            Returns task finalize settings list
        """
        finalize_settings = (
            { 'id' : 'all',      'title' : 'all involved users respond' },
            { 'id' : 'somebody', 'title' : 'somebody in department respond' },
            { 'id' : 'reviewer', 'title' : 'at least reviewer respond' },
            { 'id' : 'chief',    'title' : 'if only chief respond' },
            { 'id' : 'vip',      'title' : 'vip respond' },
            { 'id' : 'any',      'title' : 'anybody respond' },
        )
        if id:
            x = [ x['title'] for x in finalize_settings if x['id'] == id ]
            return x and x[0]
        return finalize_settings

    def mail_server( self ):
        """
            Returns mail server address
        """
        return self.MailServer.address()

    def packDBOptions( self ):
        """
            Returns database pack options from /BackupFSRoot
        """
        backupFSRoot = self._getBackupFSRoot()
        if backupFSRoot is not None:
            return backupFSRoot.getPackDBoptions()
        return {}

    def backupDBOptions( self ):
        """
            Returns database backup options from /BackupFSRoot
        """
        backupFSRoot = self._getBackupFSRoot()
        if backupFSRoot is not None:
            return backupFSRoot.getBackupDBoptions()
        return {}

    def listArchivers( self ):
        """
            Returns options from /BackupFSRoot - list possible archivers.
        """
        backupFSRoot = self._getBackupFSRoot()
        if backupFSRoot is not None:
            return backupFSRoot.listArchivers()
        return []

    def isPackTaskActive( self ):
        """
            Returns pack task state from /BackupFSRoot.
        """
        backupFSRoot = self._getBackupFSRoot()
        if backupFSRoot is not None:
            return backupFSRoot.isPackTaskActive( self.parent().absolute_url(1) )
        return 0

    def isBackupTaskActive( self ):
        """
            Returns backup task state from /BackupFSRoot.
        """
        backupFSRoot = self._getBackupFSRoot()
        if backupFSRoot is not None:
            return backupFSRoot.isBackupTaskActive( self.parent().absolute_url(1) )
        return 0

    ### Internal use only methods ###

    def _getBackupFSRoot(self):
        # tries to find & get ExpressSuiteBackup
        loop_app = self.getPhysicalRoot()
        backupFSRoot = getattr( loop_app, 'ExpressSuiteBackup', None )
        if backupFSRoot is not None:
            return backupFSRoot

        #this part is for compatibility only
        update_props = 0
        props = {}
        #try to find OLD - 'BackupFSRoot', remove it and create new - 'ExpressSuiteBackup'
        oldBackupFSRoot = getattr( loop_app, 'BackupFSRoot', None )
        if oldBackupFSRoot is not None:
            #remember its props
            update_props = 1
            props.update( oldBackupFSRoot.getPackDBoptions() )
            props.update( oldBackupFSRoot.getBackupDBoptions() )
            #remove old
            loop_app._delObject( 'BackupFSRoot' )
        #create new
        try:
            b = BackupFSRoot.BackupFSRoot()
            loop_app._setObject(b.id, b)
        except:
            return None
        if update_props:
            #update its properties
            backupFSRoot = getattr(loop_app, 'ExpressSuiteBackup', None)
            backupFSRoot.editProperties( self.parent().absolute_url(1), props )

        return backupFSRoot

    def getBackupNotifiedMembers( self ):
        """
        """
        backupFSRoot = self._getBackupFSRoot()
        if backupFSRoot is not None:
            return backupFSRoot.getNotifiedMembers()

        return 0

InitializeClass( PropertiesTool )
