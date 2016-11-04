"""
ExpressSuiteCore and PortalGenerator classes
$Id: ExpressSuiteCore.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 09/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import Zope2

import sys, os
from copy import copy
from locale import setlocale, getlocale, LC_ALL
from string import join
from urllib import splittype, splitport
from urlparse import urlparse
from types import StringType, UnicodeType

from Globals import HTMLFile, DTMLFile, package_home, get_request
from AccessControl import ClassSecurityInfo
from Acquisition import aq_get
from ZPublisher import Publish
from ZPublisher.HTTPRequest import default_port
from ZPublisher.BeforeTraverse import NameCaller, registerBeforeTraverse, queryBeforeTraverse

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.FSDTMLMethod import FSDTMLMethod
from Products.CMFCore.FSImage import FSImage
from Products.CMFCore.PortalObject import PortalObjectBase
from Products.CMFCore.DirectoryView import addDirectoryViews, createDirectoryView
from Products.CMFCore.utils import getToolByName, _checkPermission, _getAuthenticatedUser

from Products.CMFDefault import DiscussionItem, SkinnedFolder
from Products.CMFDefault import cmfdefault_globals
from Products.CMFDefault.DublinCore import DefaultDublinCoreImpl

try: from Products.AppTracker.AppTracker import AppTracker
except ImportError: AppTracker = None

from logging import getLogger
logger = getLogger( 'ExpressSuiteCore' )

import Config

if Config.IsSQLCatalog:
    import ZSQLCatalogTool as CatalogTool
    from Products.ZMySQLDA.DA import Connection as SQLConnection
else:
    import CatalogTool

import ActionsTool
import BackupFSRoot
import CommentsTool
import DTMLDocument, DefaultCategories, DepartmentDictionary
import ErrorLogTool, Exceptions, FSFile, FSFolder, Features, GuardedTable
import HTMLDocument, HTMLCard
import Mail, MailFolder, MemberDataTool, MetadataTool
import PropertiesTool, Registry, SearchProfile, ServicesTool, Shortcut
import TaskItem, TypesTool
import UserFolder

# these may need to be upgraded
#from MigrationTool import MigrationTool

from Config import Roles
from Heading import Heading, factory_type_information as Heading_factory_type_information
from ManageCMFContent import ManageCMFContent
from SimpleObjects import ContainerBase

from Utils import InitializeClass, getLanguageInfo, makepath, joinpath, pathdelim, formatComments, \
     GetSessionValue, SetSessionValue, ExpireSessionValue

import CustomDefinitions
from CustomObjects import CustomDefs, ObjectHasCustomCategory, ObjectShouldBeCleanedBeforePaste, \
     CustomCheckPermission, CustomCookedTableTranslit, getJSCleanerAttrs

factory_type_information = ( \
                             DTMLDocument.factory_type_information
                           + FSFile.factory_type_information
                           + FSFolder.factory_type_information
                           + GuardedTable.factory_type_information
                           + Heading_factory_type_information
                           + HTMLDocument.factory_type_information
                           + HTMLCard.factory_type_information
                           + MailFolder.factory_type_information
                           + Registry.factory_type_information
                           + SearchProfile.factory_type_information
                           + Shortcut.factory_type_information
                           + TaskItem.factory_type_information
                           )

DiscussionItem_fti = copy( DiscussionItem.factory_type_information )
DiscussionItem_fti[0]['disallow_manual'] = 1

SkinnedFolder_fti = copy( SkinnedFolder.factory_type_information )
SkinnedFolder_fti[0]['disallow_manual'] = 1

cmf_factory_type_information = DiscussionItem_fti + SkinnedFolder_fti


class ExpressSuiteCore( ContainerBase, PortalObjectBase, DefaultDublinCoreImpl ):
    """
        Functions of this class help in the setup of a new ExpressSuiteCore
    """
    _class_version = 1.01

    meta_type = 'ExpressSuiteCore'

    __implements__ = ( Features.isPortalRoot,
                       Features.isPrincipiaFolderish,
                       PortalObjectBase.__implements__,
                       DefaultDublinCoreImpl.__implements__,
                     )

    isPrincipiaFolderish = 1

    security = ClassSecurityInfo()

    manage_options = PortalObjectBase.manage_options + \
                     ContainerBase.manage_options

    _properties = (
        {'id':'title',           'type':'string', 'mode':'w'},
        {'id':'description',     'type':'text',   'mode':'w'},
        {'id':'server_url',      'type':'string', 'mode':'w'},
        {'id':'stemmer',         'type':'string', 'mode':'w'},
        {'id':'product_version', 'type':'string', 'mode':'w'},
    )

    # overriden by Implicit in ItemBase
    __of__ = PortalObjectBase.__of__

    # overriden by ObjectManager in ContainerBase
    _checkId = PortalObjectBase._checkId
    _verifyObjectPaste = PortalObjectBase._verifyObjectPaste

    # default attribute values
    title = ''
    description = ''
    server_url = None
    product_version = None

    service_unavailable = DTMLFile( 'dtml/service_unavailable', globals() )

    def __init__( self, id, title='' ):
        """
            Initializes class instance
        """
        ContainerBase.__init__( self )
        PortalObjectBase.__init__( self, id, title )
        DefaultDublinCoreImpl.__init__( self )

    def _initstate( self, mode ):
        """
            Initializes instance attributes
        """
        if not ContainerBase._initstate( self, mode ):
            return 0

        # install our before_traverse hook
        if not queryBeforeTraverse( self, __name__ ):
            registerBeforeTraverse( self, NameCaller('_beforeTraverseHook'), __name__ )

        if not mode:
            return 1

        if getattr( self, 'server_url', None ) is None:
            REQUEST = get_request()
            self._setPropValue( 'server_url', REQUEST and REQUEST.physicalPathToURL('') or '' )

        self._upgrade( 'portal_actions', ActionsTool.ActionsTool )
        self._upgrade( 'portal_catalog', CatalogTool.CatalogTool )
        self._upgrade( 'portal_memberdata', MemberDataTool.MemberDataTool )
        self._upgrade( 'portal_metadata', MetadataTool.MetadataTool )
        self._upgrade( 'portal_properties', PropertiesTool.PropertiesTool )
        self._upgrade( 'portal_types', TypesTool.TypesTool )

        for view in self.portal_skins.objectValues():
            if getattr( view, '_isDirectoryView', None ):
                view._dirpath = view._dirpath.replace( '\\', pathdelim )

        if not hasattr( self, 'portal_errorlog' ):
            tool = ErrorLogTool.ErrorLogTool()
            self._setObject( tool.getId(), tool )

        if not hasattr( self, 'portal_comments' ):
            tool = CommentsTool.CommentsTool()
            self._setObject( tool.getId(), tool )

        if not hasattr( self, 'portal_services' ):
            tool = ServicesTool.ServicesTool()
            self._setObject( tool.getId(), tool )

        gen = PortalGenerator()
        gen.setupMail( self )

        return 1

    def _afterValidateHook( self, user, published=None, REQUEST=None ):
        """
            Prepares global enviroment after the user is authenticated
        """
        self.setContentCharset( REQUEST )
        self.fixFormLanguage( REQUEST )

        if isinstance( published, FSImage ):
            REQUEST.RESPONSE.setHeader( 'Cache-Control', 'public, max-age=7200, must-revalidate' )
        elif isinstance( published, FSDTMLMethod ):
            REQUEST.RESPONSE.setHeader('Expires', 'Tue, 22 Jan 1980 01:01:01 GMT')

    def _beforeTraverseHook( self, container, REQUEST, *args ):
        """
            Prepares global enviroment before any object inside is accessed
        """
        try:
            self.fixProxiedRequest( REQUEST )
            self.setPortalLocale()
            self.setContentCharset( REQUEST )
        except:
            pass

        try: mpath = list( Config.MaintainanceMode.get( self._p_oid ) or [] )
        except: mpath = None
        if not mpath:
            return

        stack = REQUEST['TraversalRequestNameStack']
        mpath.reverse()

        if stack and ( stack[-1] in ['portal_errorlog', 'scripts.js', 'styles.css'] or \
                       stack[0] == 'manage' or stack[0].startswith('manage_') ):
            return

        if stack[ -len(mpath): ] != mpath:
            REQUEST['TraversalRequestNameStack'] = ['maintainance']

    def _containment_onAdd( self, item, container ):
        """
            Is called after our parent *item* is added to the *container*
        """
        # Not calling base class's methods from here avoids reinitialization
        # of all the content objects after product version change.
        # Setup is carried by generator anyway.

        # need to realize same as Scheduler schema to provide non-conflict database backup
        # if more than one ExpressSuiteCore in ZODB is presented.
        loop_app = self.getPhysicalRoot()
        if not hasattr( loop_app, 'ExpressSuiteBackup' ):
            try:
                b = BackupFSRoot.BackupFSRoot()
                loop_app._setObject( b.id, b )
            except:
                pass

    def _containment_onDelete( self, item, container ):
        """
            Is called before our parent *item* is deleted from its *container*
        """
        root = self.getPhysicalRoot()
        backupFSRoot = getattr(root, 'ExpressSuiteBackup', None)
        if backupFSRoot is not None:
            backupFSRoot.unregistryAppBackup( joinpath( item.getPhysicalPath() ) )

        PortalObjectBase.manage_beforeDelete( self, item, container )

    def _instance_onCreate( self ):
        self.product_version = Config.ProductVersion

    security.declareProtected( CMFCorePermissions.View, 'maintainance' )
    def maintainance( self, REQUEST=None ):
        """
            Maintainance mode
        """
        if _checkPermission( CMFCorePermissions.ManagePortal, self ):
            mpath = Config.MaintainanceMode.get( self._p_oid )
            return self.redirect( action='/'.join(mpath) )
        return self.service_unavailable( self, REQUEST )
    #
    #   ==========================================================================================================
    #
    def view( self, REQUEST=None ):
        """ Invokes the default view of the content storage """
        REQUEST = REQUEST or self.REQUEST
        return self.storage(REQUEST)

    security.declarePrivate( 'fixProxiedRequest' )
    def fixProxiedRequest( self, REQUEST ):
        """ Fixes environment if request was processed by frontend server """
        # mod_proxy: X-Forwarded-Server
        # mod_accel: X-Host, X-Real-IP, X-URI, X-Method
        server = REQUEST.get('SERVER_URL')
        real_host = REQUEST.get('HTTP_X_FORWARDED_SERVER') or REQUEST.get('HTTP_X_HOST')
        real_addr = REQUEST.get('HTTP_X_REAL_IP')
        real_uri = REQUEST.get('HTTP_X_URI')

        # change SERVER_URL to frontend server's address and protocol
        if server and real_host:
            proto = REQUEST.get('HTTP_X_METHOD') or splittype( server )[0]
            host, port = splitport( real_host )
            REQUEST.setServerURL( proto, host, port or default_port.get( proto ) )

        # set REMOTE_ADDR to the real client's address
        if real_addr:
            REQUEST.environ['REMOTE_ADDR'] = real_addr

        # modify SCRIPT_NAME for proxied requests like
        # http://frontend/prefix/portal -> http://backend/portal
        if real_uri:
            # TODO: handle different portal name on frontend
            pos = real_uri.find( REQUEST['PATH_INFO'] )
            if pos > 0:
                REQUEST._script = real_uri[ 1:pos ].split('/')

    security.declarePrivate( 'setPortalLocale' )
    def setPortalLocale( self ):
        """ Changes system locale according to the portal language """
        info = getLanguageInfo( self )

        # find default and effective locale settings
        def_locale = info.get( sys.platform + '_locale' ) or info.get( os.name + '_locale' )
        cur_locale = getlocale()
        cur_locale = None not in cur_locale and '.'.join( cur_locale ) or ''

        # check whether locale is already ok
        if def_locale is None or cur_locale.lower() == def_locale.lower():
            return

        # change effective locale
        try:
            setlocale( LC_ALL, def_locale )
        except Exceptions.LocaleError:
            pass

    security.declarePublic( 'setContentCharset' )
    def setContentCharset( self, REQUEST=None ):
        """ Sets response charset according to the user's selected language """
        REQUEST = REQUEST or aq_get( self, 'REQUEST', None )
        if REQUEST is None:
            return

        lang = REQUEST.cookies.get( 'LOCALIZER_LANGUAGE' )
        info = getLanguageInfo( lang, None )

        if lang is None or info is None:
            membership = getToolByName( self, 'portal_membership', None )
            if membership is not None:
                lang = membership.getLanguage( preferred=1, REQUEST=REQUEST )
                info = getLanguageInfo( lang )
                REQUEST.set( 'LOCALIZER_LANGUAGE', lang )
                if not membership.isAnonymousUser():
                    path = joinpath( '', REQUEST._script, self.absolute_url( relative=1 ) )
                    REQUEST.RESPONSE.setCookie( 'LOCALIZER_LANGUAGE', lang, path=path )

        charset = info['http_charset']
        REQUEST.set( 'LOCALIZER_CHARSET', charset )
        REQUEST.set( 'management_page_charset', charset )
        REQUEST.RESPONSE.setHeader( 'content-type', 'text/html; charset=%s' % charset )

    security.declarePublic( 'fixFormLanguage' )
    def fixFormLanguage( self, REQUEST ):
        """
            Replaces HTML-encoded entities with their corresponding
            characters in the POST form data
        """
        if REQUEST is None:
            return

        lang = REQUEST.get( 'LOCALIZER_LANGUAGE' )
        map = Config.LanguageEntitiesMap.get( lang )
        if map is None:
            return

        for key, value in REQUEST.form.items():
            if type(value) in ( StringType, UnicodeType, ):
                for entity, char in map.items():
                    value = value.replace( entity, char )
                REQUEST.form[ key ] = value

        if REQUEST.REQUEST_METHOD == 'PUT':
            value = REQUEST.other.get('BODY')
            if value is not None:
                for entity, char in map.items():
                    value = value.replace( entity, char )
                REQUEST.other['BODY'] = value

    security.declareProtected( CMFCorePermissions.View, 'isEffective' )
    def isEffective( self, date ):
        """ Override DefaultDublinCoreImpl's test, since we are always viewable """
        return 1

    def reindexObject( self, idxs=[] ):
        """ Overrides DefaultDublinCoreImpl's method """
        pass

    def productVersion( self ):
        """ Returns version string of the product """
        return Config.ProductVersion
    #
    #   Portal global utilities ==================================================================================
    #
    security.declarePublic( 'getPortalObject' )
    def getPortalObject( self ):
        """ Returns the portal object itself """
        return self

    security.declarePublic( 'getPortalConfiguration' )
    def getPortalConfiguration( self ):
        """ Returns the PortalConfiguration object """
        return CustomDefinitions.portalConfiguration

    security.declarePublic( 'getDepartmentDictionary' )
    def getDepartmentDictionary( self ):
        """ Returns the DepartmentDictionary object """
        return DepartmentDictionary.departmentDictionary

    security.declarePublic( 'getCustomDefinitions' )
    def getCustomDefinitions( self, defs, *args, **kw ):
        """ Returns given custom definition value """
        return CustomDefs( defs, *args, **kw )

    security.declarePublic( 'hasCustomCategory' )
    def hasCustomCategory( self, context ):
        """ Returns given custom definition value """
        return ObjectHasCustomCategory( context )

    def shouldBeCleanedBeforePaste( self, context ):
        """ Verifies whether content body should be cleaned before paste """
        return ObjectShouldBeCleanedBeforePaste( context )

    security.declarePublic( 'getJSCleanerForCategory' )
    def getJSCleanerAttrsForCategory( self, context, category, **kw ):
        """ Returns js cleaner attrs """
        return getJSCleanerAttrs( context, category, **kw )

    security.declarePublic( 'getCustomCookedTableTranslit' )
    def getCustomCookedTableTranslit( self, context, id, values ):
        """ Returns translitted custom data table values """
        return CustomCookedTableTranslit( context, id, values )

    security.declarePublic( 'getFormattedComments' )
    def getFormattedComments( self, text, mode=None ):
        """ Returns formatted comments text """
        return formatComments( text, mode )

    security.declarePublic( 'hasCustomPermissions' )
    def hasCustomPermissions( self, context, permission ):
        """ Returns given custom definition value """
        return CustomCheckPermission( context, permission )

    security.declarePublic( 'getSession' )
    def getSession( self, name, default=None, REQUEST=None, cookie=None ):
        """ Returns session data value """
        return GetSessionValue( self, name, default, REQUEST, cookie )

    security.declarePublic( 'setSession' )
    def setSession( self, name, value, REQUEST=None, cookie=None ):
        """ Stores session data value """
        SetSessionValue( self, name, value, REQUEST, cookie )

InitializeClass( ExpressSuiteCore )


class PortalGenerator:

    klass = ExpressSuiteCore

    def setupTools( self, p ):
        """
            Setup initial tools
        """
        addCMFCoreTool = p.manage_addProduct['CMFCore'].manage_addTool
        addCMFCoreTool( 'CMF Skins Tool', None )
        addCMFCoreTool( 'CMF Undo Tool', None )
        addCMFCoreTool( 'CMF URL Tool', None )

        addCMFDefaultTool = p.manage_addProduct['CMFDefault'].manage_addTool
        addCMFDefaultTool( 'Default Discussion Tool', None )
        addCMFDefaultTool( 'Default Registration Tool', None )

        addExpressSuiteTool = p.manage_addProduct['ExpressSuiteTools'].manage_addTool
        addExpressSuiteTool( 'ExpressSuite Actions Tool', None )
        addExpressSuiteTool( 'ExpressSuite Catalog Tool', None )
        addExpressSuiteTool( 'ExpressSuite Comments Tool', None )
        addExpressSuiteTool( 'ExpressSuite DocumentLink Tool', None )
        addExpressSuiteTool( 'ExpressSuite ErrorLog Tool', None )
        addExpressSuiteTool( 'ExpressSuite Followup Actions Tool', None )
        addExpressSuiteTool( 'ExpressSuite Help Tool', None )
        addExpressSuiteTool( 'ExpressSuite Member Data Tool', None )
        addExpressSuiteTool( 'ExpressSuite Membership Tool', None )
        addExpressSuiteTool( 'ExpressSuite Metadata Tool', None )
        addExpressSuiteTool( 'ExpressSuite Properties Tool', None )
        addExpressSuiteTool( 'ExpressSuite Types Tool', None )
        addExpressSuiteTool( 'ExpressSuite Workflow Tool', None )
        addExpressSuiteTool( 'ExpressSuite Services Tool', None )
        addExpressSuiteTool( 'Portal Scheduler Tool', None )

        #addExpressSuiteTool( 'ExpressSuite Migration Tool', None )

    def setupMessageCatalog( self, p, language ):
        langs = Config.Languages
        p.manage_addProduct['Localizer'].manage_addMessageCatalog( 'msg', 'Messages', langs.keys())

        msg = p._getOb( 'msg' )
        path = joinpath( package_home( globals() ), 'locale' )

        msg.manage_changeDefaultLang( language or Config.DefaultLanguage )

        for lang, info in langs.items():
            charset = info['python_charset'].upper()
            msg.update_po_header( lang, '', '', '', charset )

            # import PO file into the Message Catalog
            try:
                file = open( joinpath( path, '%s.po' % lang ), 'rt' )
            except IOError:
                pass
            else:
                msg.manage_import( lang, file )
                file.close()

                # fix empty string (just in case...)
                msg.manage_editLS( '', (lang, '') )

        # select default language
        p.setPortalLocale()
        p.setContentCharset()

    def setupMail( self, p ):
        """
            Create mail objects
        """
        mh = getattr( p, 'MailHost', None )
        if not ( mh is None or isinstance( mh, Mail.MailServerBase ) ):
            p._delObject( 'MailHost' )
            mh = None

        if mh is None:
            Mail.manage_addMailSender( p, 'MailHost', host='' )

        if getattr( p, 'MailServer', None ) is None:
            Mail.manage_addMailServer( p, 'MailServer', host='' )

    def setupUserFolder( self, p ):
        p.manage_addProduct['ExpressSuiteTools'].addUserFolder()

    def setupCookieAuth( self, p ):
        p.manage_addProduct['CMFCore'].manage_addCC( id='cookie_authentication' )
        p.cookie_authentication.auto_login_page = ''

    def setupRoles( self, p ):
        p.__ac_roles__ = ( 'Member', 'Visitor', 'Editor', 'Writer', 'Reader', 'Author', 'VersionOwner' )

    def setupPermissions( self, p ):
        """
            Setup some suggested roles to permission mappings
        """
        mp = p.manage_permission
        for entry in Config.PortalPermissions:
            apply( mp, entry )

    def setupDefaultSkins( self, p ):
        """
            Setup portal skins
        """
        pstool = getToolByName( p, 'portal_skins', None )
        #pstool = getattr( p, 'portal_skins', None )
        if pstool is None:
            return

        cmf_manager = ManageCMFContent()
        for view in Config.SkinViews:
            cmf_manager.register_view( pstool, 'skins/%s' % view )

        # these skin elements are available for anonymous visitors
        #for name in Config.PublicViews:
        #    pstool[ name ].manage_permission( CMFCorePermissions.View, [Roles.Anonymous], 1 )

        addDirectoryViews( pstool, 'skins', cmfdefault_globals )
        pstool.manage_addProduct['OFSP'].manage_addFolder( id='custom' )
        default_skins = ', '.join( ['custom'] + Config.SkinViews )

        pstool.addSkinSelection( 'Site', default_skins, make_default=1 )
        pstool.addSkinSelection( 'Mail', 'mail_templates' )

        p.setupCurrentSkin()

    def setupTypes( self, p, initial_types=factory_type_information ):
        """
            Setup portal types
        """
        tptool = getToolByName( p, 'portal_types', None )
        #tptool = getattr( p, 'portal_types', None )
        if tptool is None:
            return
        for x in initial_types:
            if not tptool.getTypeInfo( x['id'] ):
                tptool.addType( x['id'], x )

    def setupCategories( self, p, categories=None, **kw ):
        """
            Setup default categories
        """
        metadata = getToolByName( p, 'portal_metadata', None )
        if metadata is None:
            return

        if not categories:
            categories = ['Document', 'SimpleDocs']

        default_categories = DefaultCategories.DefaultCategories()

        for id in categories:
            if metadata.getCategoryById( id ):
                continue
            category = DefaultCategories.setupCategory( default_categories, id, metadata )
            if category is None:
                continue
            workflow = category.getWorkflow()
            if workflow is None:
                continue
            DefaultCategories.setupWorkflow( default_categories, workflow, id, metadata )

        del default_categories

    def setupMimetypes( self, p ):
        """
            Setup mime types
        """
        p.manage_addProduct[ 'CMFCore' ].manage_addRegistry()
        reg = p.content_type_registry

        reg.addPredicate( 'dtml', 'extension' )
        reg.getPredicate( 'dtml' ).edit( extensions="dtml" )
        reg.assignTypeName( 'dtml', 'DTMLDocument' )

        reg.addPredicate( 'link', 'extension' )
        reg.getPredicate( 'link' ).edit( extensions="url, link" )
        reg.assignTypeName( 'link', 'Link' )

        reg.addPredicate( 'news', 'extension' )
        reg.getPredicate( 'news' ).edit( extensions="news" )
        reg.assignTypeName( 'news', 'News Item' )

        reg.addPredicate( 'document', 'major_minor' )
        reg.getPredicate( 'document' ).edit( major="text", minor="" )
        reg.assignTypeName( 'document', 'HTMLDocument' )

        reg.addPredicate( 'image', 'major_minor' )
        reg.getPredicate( 'image' ).edit( major="image", minor="" )
        reg.assignTypeName( 'image', 'Site Image' )

        reg.addPredicate( 'file', 'major_minor' )
        reg.getPredicate( 'file' ).edit( major="application", minor="" )
        reg.assignTypeName( 'file', 'File' )

    def setupWorkflow( self, p, check=0 ):
        """
            Setup default workflow
        """
        workflow = getToolByName( p, 'portal_workflow', None )
        tptool = getToolByName( p, 'portal_types', None )
        if workflow is None or tptool is None:
            return
        cbt = workflow._chains_by_type

        count = 0
        seen = []
        for chain, types in Config.WorkflowChains.items():
            seen.extend( types )
            for pt in types:
                if not cbt or cbt.get( pt ) != chain:
                    count += 1

        if not check:
            wf_id = 'heading_workflow'
            workflow.createWorkflow( wf_id )
            workflow.setChainForPortalTypes( Config.WorkflowChains['heading_workflow'], ( wf_id, ) )
            workflow.setChainForPortalTypes( Config.WorkflowChains['__empty__'], ('', ) )

            DefaultCategories.setupHeadingWorkflow( workflow.getWorkflowById( wf_id ) )

        return count

    def setupDefaultMembers( self, p, lang='ru' ):
        """
            Adds default members and groups
        """
        membership = getToolByName( p, 'portal_membership', None )
        msg = getToolByName( p, 'msg', None )
        if None in ( membership, msg ):
            return None

        membership._addGroup( 'all_users', msg.gettext( 'All users', lang=lang ) )
        membership._addGroup( '_managers_', msg.gettext( 'Managers', lang=lang ) )

        username = None
        try: username = _getAuthenticatedUser().getUserName()
        except: pass
        if not username:
            username = 'admin'
        roles = ( 'Member', 'Manager', )
        properties = { 'lname' : msg.gettext( 'admin', lang=lang ) }
        membership.addMember( id=username, password='123', roles=roles, domains='', properties=properties )
        member = membership.getMemberById( username )
        if member is None:
            return None
        users = [ username ]

        membership.manage_changeGroup( group='all_users', group_users=users )
        membership.manage_changeGroup( group='_managers_', group_users=users )

        return member

    def setupStorage( self, p, create_userfolder=None ):
        """
            Setup storage folders
        """
        if p is None:
            return
        base = p.manage_addProduct['ExpressSuiteTools']
        if base is None:
            return
        msg = getToolByName( p, 'msg', None )
        if msg is None:
            return

        lang = msg.get_default_language()

        member = create_userfolder and self.setupDefaultMembers( p, lang ) or None

        storage = self._makeHeading( p.manage_addProduct['ExpressSuiteTools'], 'storage', \
                        msg.gettext( 'Content storage', lang=lang ) )

        if storage:
            self._makeHeading( p.storage.manage_addProduct['ExpressSuiteTools'], 'members', \
                        msg.gettext( 'Home folders', lang=lang ) )
            self._makeHeading( p.storage.manage_addProduct['ExpressSuiteTools'], 'user_defaults', \
                        msg.gettext( 'Default content', lang=lang ) )
            system = self._makeHeading( p.storage.manage_addProduct['ExpressSuiteTools'], 'system', \
                        msg.gettext( 'System folders', lang=lang ) )
        else:
            system = None

        if system:
            self._makeHeading( p.storage.system.manage_addProduct['ExpressSuiteTools'], 'templates', \
                        msg.gettext( 'Document templates', lang=lang ) )

        if storage:
            mp = p.storage.manage_permission
            mp('List folder contents', ['Owner','Manager', 'Editor', 'Writer', 'Reader', 'Author'], 0)
            mp('View', ['Owner','Manager', 'Member'], 1)

        if create_userfolder and member is not None:
            home = member.getHomeFolder( create=1 )

        # add access rights for system folder
        if system:
            p.storage.system.manage_setLocalGroupRoles( 'all_users', ['Reader'] )
        if storage:
            if member is not None:
                p.storage.changeOwnership( member, recursive=1 )
            p.storage.reindexObject( recursive=1 ) #idxs=['allowedRolesAndUsers'], 

    def setupTracker( self, p ):
        """
            Setup tracker
        """
        pass

    def setupActions( self, p ):
        """
            Setup portal actions
        """
        actions = getToolByName( p, 'portal_actions', None )
        if actions is None:
            return

        actions.action_providers = ( \
                'portal_comments'
              , 'portal_discussion'
              , 'portal_help'
              , 'portal_membership'
              , 'portal_metadata'
              , 'portal_properties'
              , 'portal_registration'
              , 'portal_services'
              , 'portal_scheduler'
              , 'portal_undo'
              , 'portal_workflow'
        )

    def setupCatalog( self, p ):
        """
            Setup portal catalogs
        """
        tool_ids = ( 'portal_catalog', 'portal_followup', 'portal_links', )
        for id in tool_ids:
            ob = getToolByName( p, id, None )
            if ob is None:
                return
            if Config.IsSQLCatalog and ob.implements('IZSQLCatalog'):
                ob.sql_db_name = p.getId()
                ob.sql_prefix = ''.join([ x[0:1] for x in id.split('_') ] )
                ob.sql_root = '_Root'
                ob.sql_user = Config.SQLDBUser
                ob.setup()

            ob.setupIndexes()

    def setup( self, p, language, create_userfolder ):
        """
            Setup portal object
        """
        logger.info('Setup new ExpressSuite instance, id: %s, IsSQLCatalog: %s' % ( p.getId(), Config.IsSQLCatalog ) )

        if Config.IsSQLCatalog:
            id = Config.SQLDBConnectorID
            addZMySQLConnection( p, id, 'Z MySQL Database Connection', 1 )

        self.setupTools( p )
        self.setupCatalog( p )
        self.setupMessageCatalog( p, language )
        self.setupMail( p )

        if int(create_userfolder) != 0: self.setupUserFolder( p )

        self.setupCookieAuth( p )
        self.setupRoles( p )
        self.setupPermissions( p )
        self.setupDefaultSkins( p )

        # SkinnedFolders are only for customization;
        # they aren't a default type.
        default_types = tuple( filter( lambda x: x['id'] != 'Skinned Folder', factory_type_information ) )
        self.setupTypes( p, default_types )
        self.setupTypes( p, cmf_factory_type_information )

        self.setupCategories( p )
        self.setupMimetypes( p )
        self.setupWorkflow( p )
        self.setupActions( p )
        self.setupManual( p, 'manual' )

        logger.info('Successfully created new instance')

    def setupManual( self, target, path, ctype=None ):
        """
            Setup manual
        """
        createDirectoryView( target, makepath( path ) )

    def create( self, parent, id, language, create_userfolder ):
        """
            Creates an instance
        """
        id = str(id)
        portal = self.klass( id=id )
        parent._setObject( id, portal )

        # Return the fully wrapped object
        p = parent.this()._getOb( id )
        self.setup( p, language, create_userfolder )
        return p

    def setupDefaultProperties( self, p, id, title, description, email_from_address, email_from_name,
                                validate_email, server_url, stemmer ):
        """
            Setup default portal properties
        """
        p._setProperty( 'email_from_address', email_from_address, 'string' )
        p._setProperty( 'email_from_name', email_from_name, 'string' )
        p._setProperty( 'validate_email', validate_email and 1 or 0, 'boolean' )
        p._setProperty( 'email_antispam', '', 'string' )
        p._setProperty( 'email_error_address', '', 'string' )
        p._setProperty( 'instance', id, 'string' )
        p._setProperty( 'remote_url', '', 'string' )

        p._setProperty( 'apply_threading', 1, 'boolean' )
        p._setProperty( 'use_timeout', 1, 'boolean' )
        p._setProperty( 'duration', 0.001, 'float' )
        p._setProperty( 'p_resolve_conflict', 0, 'boolean' )

        p._setProperty( 'max_involved_users', 10, 'int' )
        p._setProperty( 'service_timeout', 30, 'int' )
        p._setProperty( 'created_search_interval', 999, 'int' )
        p._setProperty( 'common_url', '', 'string' )

        p._setProperty( 'send_to_support', 0, 'boolean' )
        p._setProperty( 'member_activity', 1, 'boolean' )
        p._setProperty( 'emergency_service', 0, 'boolean' )
        p._setProperty( 'p_log', 0, 'boolean' )

        p._setProperty( 'suspended_mail', 1, 'boolean' )
        p._setProperty( 'mail_frequency', 1, 'int' )
        p._setProperty( 'mail_threshold', 500, 'int' )

        p._setPropValue( 'server_url', server_url )
        p._setPropValue( 'stemmer', stemmer )

        p.title = title
        p.description = description

    def setupAfterCreate( self, p, create_userfolder ):
        """
            Setup portal catalog and folders storage
        """
        self.setupStorage( p, create_userfolder )

    def _makeHeading( self, ob, id, title=None ):
        """
            Creates Heading instance
        """
        try:
            folder = Heading( id=id, title=title )
            if folder is not None:
                ob._setObject( id, folder, set_owner=1 )
                return 1
        except:
            raise
        return 0


def addZMySQLConnection( dispatcher, id, title='', check=None ):
    """
        Adds MySQL DB Connection
    """
    connection_string = '-mysql root'
    conn = SQLConnection( id, title, connection_string, check )

    if conn.connected():
        DB = conn._v_database_connection
        if DB is not None and DB.is_opened():
            instance = dispatcher.getId()
            if instance:
                DB.query( "CREATE DATABASE IF NOT EXISTS %s" % instance )

            acl_users = aq_get(dispatcher, 'acl_users', None, 1)
            if acl_users is not None:
                userid = Config.SQLDBUser
                user = acl_users.getUserById( userid )
                passwd = user.__
                servers = ( 'localhost', '%', )

                for x in servers:
                    DB.query( "GRANT ALL PRIVILEGES ON %s.* TO '%s'@'%s' IDENTIFIED BY '%s' WITH GRANT OPTION" % ( \
                       instance, userid, x, passwd ) )
                    DB.query( "SET PASSWORD FOR '%s'@'%s' = OLD_PASSWORD('%s')" % ( \
                       userid, x, passwd ) )

            DB.close()

            if instance and userid:
                connection_string = Config.connection_string % { \
                    'instance' : instance,
                    'user'     : userid,
                    'passwd'   : passwd
                }

            Publish.setupProduct( DB, connection_string, dispatcher )

    dispatcher._setObject(id, conn)

def manage_addExpressSuiteForm( self ):
    """
        Returns ExpressSuite instance generator form
    """
    add_expresssuite_form = HTMLFile('dtml/addExpressSuite', globals())

    all_languages = []
    for lang, info in Config.Languages.items():
        all_languages.append( {
                'id' : lang,
                'title' : info['title'],
                'default' : lang == Config.DefaultLanguage,
            } )

    try:
        from Products.TextIndexNG2 import allStemmers
        all_stemmers = allStemmers(self)
    except ImportError:
        all_stemmers = []

    return add_expresssuite_form( self, all_languages=all_languages, all_stemmers=all_stemmers )

#manage_addExpressSuiteForm.__name__ = 'addExpressSuite'

def manage_addExpressSuite( self, id='common', title='Express Suite DMS', description='',
                            create_userfolder=1,
                            email_from_address=None,
                            email_from_name=None,
                            validate_email=0,
                            language=None,
                            stemmer=None,
                            REQUEST=None
                            ):
    """
        Adds ExpressSuite instance
    """
    id = id.strip()
    server_url = self.getPhysicalRoot().absolute_url()

    if email_from_address is None:
        email_from_address = 'postmaster@%s' % urlparse( server_url )[1].split(':')[0]
    if email_from_name is None:
        email_from_name = title

    gen = PortalGenerator()
    p = gen.create( self, id, language, create_userfolder )

    gen.setupDefaultProperties( p, id, title, description, email_from_address, email_from_name,
                                validate_email, server_url, stemmer )

    gen.setupAfterCreate( p, create_userfolder )

    if REQUEST is not None:
        REQUEST.RESPONSE.redirect(p.absolute_url() + '/finish_site_construction')
