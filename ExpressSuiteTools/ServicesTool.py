"""
Portal Services tool
$Id: ServicesTool.py, v 1.0 2008/01/17 12:00 Exp $

*** Checked 06/05/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import sys, os, re
from DateTime import DateTime
from types import ListType, TupleType, IntType, StringType
from string import lower

import threading
import transaction
import xmlrpclib

from Acquisition import aq_base, aq_parent
from AccessControl import ClassSecurityInfo
from OFS.SimpleItem import SimpleItem

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.ActionInformation import ActionInformation
from Products.CMFCore.Expression import Expression
from Products.CMFCore.utils import getToolByName, _getAuthenticatedUser

import Config
from SimpleObjects import ToolBase
from Heading import Heading
from DepartmentDictionary import departmentDictionary
from Config import AuthorRole, ReaderRole, WriterRole, EditorRole, WorkflowChiefRole
from TemporalExpressions import DateTimeTE, UniformIntervalTE
from TransactionManager import interrupt_thread

from Utils import InitializeClass, getLanguageInfo, addQueryString, get_param

from CustomDefinitions import portalConfiguration, DefaultSegment, IsDefaultCompany

from logging import getLogger
logger = getLogger( 'ServicesTool' )

apps = ZOPE_HOME.find('apps')
EXPORT_HOME = ( apps > -1 and ZOPE_HOME[:apps] or ZOPE_HOME+os.sep ) + os.path.join('export','manage')


class ServicesTool( ToolBase ):
    """
        Portal services tool
    """
    _class_version = 1.25

    id = 'portal_services'
    meta_type = 'ExpressSuite Services Tool'

    security = ClassSecurityInfo()

    _actions = (
        ActionInformation(id='sync_tools'
                        , title='Sync portal tools'
                        , description="""Performs syncronization application tools between portal instances"""
                        , action=Expression( text='string: ${portal_url}/sync_portal_form' )
                        , permissions=(CMFCorePermissions.ManagePortal,)
                        , category='global'
                        , condition=None
                        , visible=1
                        ),
        ActionInformation(id='manage_archive'
                        , title='Manage portal archive'
                        , description="""Performs export/import archive actions for the instance"""
                        , action=Expression( text='string: ${portal_url}/manage_archive_form' )
                        , permissions=(CMFCorePermissions.ManagePortal,)
                        , category='global'
                        , condition=None
                        , visible=1
                        ),
        )

    def __init__( self ):
        """
            Initialize class instance
        """
        ToolBase.__init__( self )
        # Archive attributes
        self.archive_selected_categories = []
        self.archive_expired_options = {}
        self.archive_period = ()

    def _initstate( self, mode ):
        """ 
            Initializes attributes
        """
        if not ToolBase._initstate(self, mode):
            return 0

        if getattr( self, 'archive_selected_categories', None ) is None:
            self.archive_selected_categories = []
        if getattr( self, 'archive_expired_options', None ) is None:
            self.archive_expired_options = {}
        if getattr( self, 'archive_period', None ) is None:
            self.archive_period = {}
        if getattr( self, '_import_archive_log', None ) is not None:
            import_archive_log = []
            for x in self._import_archive_log:
                item = list(x)
                if type(x[4]) == type(''):
                    item[4] = [ x[4] ]
                if len(x) <> 7:
                    if len(x) == 5:
                        item.append( 'successfully' not in x[4] and 1 or 0 )
                    if len(x) <= 6:
                        item.append( None )
                import_archive_log.append( item )
            self._import_archive_log = import_archive_log
        else:
            self._import_archive_log = []

        return 1

    def sync_property( self, method, state, service, no_raise, *args ):
        """
            Sync update property
        """
        IsError = 0
        res = []
        for addr in portalConfiguration.getAttribute( attr='remote_portal_addresses', \
                key='anonymous', state=state, \
                context=self ):
            try:
                remote_services = xmlrpclib.Server( '%s/%s' % ( addr, service or 'portal_services' ) )
                IsError, x = apply( getattr( remote_services, method ), args )
                res.append( x )
            except:
                logger.error('sync_property Synchronizing error: instance %s, args: %s' % ( addr, str(args) ))
                IsError = 1
                if not no_raise:
                    raise
        return ( IsError, res, )

    def _run( self, command, message=None):
        """
            Run system command
        """
        if os.name != 'posix':
            if command.startswith('cp'):
                command = 'copy'+command[2:]
            elif command.startswith('mv'):
                command = 'move'+command[2:]
            elif command.startswith('mkdir'):
                command = 'mkdir'+command[5:]
        code = os.system(command)
        if code:
            raise 'BError', 'Error while run %s, code: %s, command: %s' % ( message or 'command', str(code), command )
        return code

    def _log( self, id, message=None ):
        """
            Log system message
        """
        if not message:
            return
        suffix = 'log'
        now = DateTime().strftime( '%Y-%m-%d %H:%M:%S' )
        instance = self.getPortalObject().getId()
        try:
            filepath = os.path.join(EXPORT_HOME, '%s.%s' % (id, suffix))
            f = open(filepath, 'a')
            f.write( "%s [%s] %s\n" % ( now, instance, message ) )
            f.close()
        except: 
            raise #pass

    def _getBackupFSRoot( self ):
        """
            Returns BackupFSRoot portal tool
        """
        try:
            p = getToolByName( self, 'portal_properties', None )
            backupFSRoot = p._getBackupFSRoot()
            return ( backupFSRoot, p.parent().absolute_url(1), )
        except Exception, msg_error:
            self._log('archive', message=str(msg_error))
            return ( None, '', )

    def getSyncOptions( self, id ):
        """
            Returns sync options
        """
        if not id:
            return None
        if id.lower() == 'memberdata':
            return { \
                'EXPORT_HOME' : EXPORT_HOME,
                'description' : "Performs syncronization of acl_users and portal_memberdata tools between portal instances",
                'ids'         : ( 'acl_users', 'portal_memberdata', ),
                'folder_to'   : 'members',
                'mask'        : '%Y%m%d-%H%M%S',
                'suffix'      : 'zexp',
            }
        if id.lower() == 'msg':
            return { \
                'EXPORT_HOME' : EXPORT_HOME,
                'description' : "Performs syncronization of message catalogs between portal instances",
                'ids'         : ( 'msg', 'msg_words', ),
                'folder_to'   : 'msg',
                'mask'        : '%Y%m%d-%H%M%S',
                'suffix'      : 'zexp',
            }
        if id.lower() == 'create_home_folders':
            return { \
                'description' : "Checks and creates new and lost member's home folders",
                'inputs'      : None,
                'submits'     : ( \
                    { 'id':'check',    'title':'Check',              'value':0, 'style':'width:100px' }, \
                    { 'id':'run',      'title':'Create lost',        'value':1, 'style':''            }, \
                ),
                'action'      : 'createHomeFolders'
            }
        if id.lower() == 'create_department_folders':
            membership = getToolByName( self, 'portal_membership', None )
            return { \
                'description' : "Checks and creates new and lost department's folders",
                'inputs'        : ( \
                    { 'name'      : 'department',
                      'title'     : 'Department',
                      'type'      : 'mapping',
                      'sort'      : 'title',
                      'onchange'  : '',
                      'values'    : departmentDictionary.listDepartments(no_break=1) }, \
                    { 'name'      : 'editor',
                      'title'     : 'Editor',
                      'type'      : 'user_list',
                      'size'      : 5,
                      'onchange'  : '',
                      'values'    : membership.getGroupMembers( '_editors_' ) }, \
                    { 'name'      : 'create_IO_shortcuts',
                      'label'     : 'Create department IO shortcuts',
                      'type'      : 'checkbox',
                      'values'    : 1, }, \
                    { 'name'      : 'set_roles',
                      'label'     : 'Check and validate members permissions',
                      'type'      : 'checkbox',
                      'values'    : 0, }, \
                    { 'name'      : 'set_postfix',
                      'label'     : 'Set valid department postfix',
                      'type'      : 'checkbox',
                      'values'    : 1, }, \
                ),
                'submits'       : ( \
                    { 'id':'run',      'title':'Create folders',     'value':1, 'style':'width:100px' }, \
                ),
                'action'      : 'createDepartmentFolders'
            }
        if id.lower() == 'set_workflow_chiefs':
            membership = getToolByName( self, 'portal_membership', None )
            return { \
                'description' : "Checks and creates new and lost department's workflow chiefs",
                'inputs'        : ( \
                    #{ 'name'      : 'company', 
                    #  'title'     : 'Company', 
                    #  'type'      : 'mapping',
                    #  'sort'      : 'title',
                    #  'onchange'  : 'javascript:changeCompany();',
                    #  'values'    : departmentDictionary.listCompanies() }, \
                    { 'name'      : 'department',
                      'title'     : 'Department',
                      'type'      : 'mapping',
                      'sort'      : 'title',
                      'onchange'  : '',
                      'values'    : departmentDictionary.listDepartments(no_break=1) }, \
                    { 'name'      : 'member',
                      'title'     : 'User',
                      'type'      : 'user_list',
                      'size'      : 5,
                      'onchange'  : '',
                      'values'    : membership.getGroupMembers( '_workflow_chiefs_' ) }, \
                    { 'name'      : 'recursive',
                      'label'     : 'Set permissions for all objects recursively',
                      'type'      : 'checkbox',
                      'values'    : 0, }, \
                ),
                'submits'       : ( \
                    { 'id':'run',      'title':'Assign permissions', 'value':1, 'style':'width:100px' }, \
                ),
                'action'      : 'setWorkflowChiefs'
            }
        if id.lower() == 'set_access_level':
            membership = getToolByName( self, 'portal_membership', None )
            access_levels = []
            for x in portalConfiguration.getAccessLevels():
                access_levels.append( { 'id'    : x['id'], \
                                        'title' : "Set '%s' access level" % x['title'], \
                                        'value' : 0 } )
            if access_levels:
                access_levels.append( { 'id'    : 'X', \
                                        'title' : 'Disable access', \
                                        'value' : 1 } )
            return { \
                'description' : "Sets new access level for given user's group",
                'inputs'        : ( \
                    { 'name'      : 'instance',
                      'title'     : 'Portal instance',
                      'type'      : 'mapping',
                      'sort'      : 'id',
                      'onchange'  : '',
                      'values'    : portalConfiguration.getAttribute( attr='instances', key='mapping' ) }, \
                    { 'name'      : 'group',
                      'title'     : 'User group',
                      'type'      : 'mapping',
                      'sort'      : 'title',
                      'onchange'  : '',
                      'values'    : membership.getListGroups( keys=('id', 'title') ) }, \
                    { 'name'      : 'level',
                      'title'     : 'Access level',
                      'type'      : 'radio',
                      'sort'      : '',
                      'onchange'  : '',
                      'values'    : access_levels }, \
                ),
                'submits'       : ( \
                    { 'id':'check',    'title':'Check',              'value':0, 'style':'width:100px' }, \
                    { 'id':'run',      'title':'Set access level',   'value':1, 'style':'' }, \
                ),
                'action'      : 'setAccessLevel'
            }
        if id.lower() == 'manage_import_archive':
            return { \
                'description' : "Creates scheduler tasks for import archiving actions for the current instance",
                'submits'     : ( 'Apply', ),
                'action'      : 'manageImportArchive',
            }
        if id.lower() == 'manage_export_archive':
            return { \
                'description' : "Performs export archiving actions for the current instance",
                'submits'     : ( 'Check', 'Export to archive', 'Apply', ),
                'action'      : 'manageExportArchive',
            }
        return None

    security.declareProtected( CMFCorePermissions.ManagePortal, 'runSyncPortalTools' )
    def runSyncPortalTools( self, id, mode=None, import_from=None, REQUEST=None ):
        """
            Performs syncronization tools between portal instances
        """
        uname = _getAuthenticatedUser(self).getUserName()
        portal = self.getPortalObject()

        logger.info('runSyncPortalTools started by %s' % uname )

        message = ''
        IsError = 0

        options = self.getSyncOptions(id)
        if REQUEST is not None and REQUEST.get('update_options', None):
            pass

        ids = options['ids']
        folder_to = options['folder_to']
        mask = options['mask']
        suffix = options['suffix']

        try:
            if not mode:
                export_home = options['EXPORT_HOME']
                export_to = os.path.join(export_home, folder_to)
                now = DateTime().strftime( mask )

                if os.access(export_to, os.F_OK|os.W_OK):
                    self._run('mv %s %s' % ( export_to, os.path.join(export_home, now+'-'+id) ), 'moving')

                self._run('mkdir %s' % export_to, 'creating export folder')

                for oid in ids:
                    ob = portal._getOb(oid)
                    if ob is None: continue

                    f = os.path.join(export_to, '%s.%s' % ( oid, suffix ))
                    ob._p_jar.exportFile(ob._p_oid, f)

                IsError, res = self.sync_property( 'runSyncPortalTools', (0,2), None, 0, id, 1, export_to )

            else:
                #import_from = get_param('import_from', REQUEST, kw, None)
                import_to = os.path.join(INSTANCE_HOME, 'import')

                for oid in ids:
                    filename = '%s.%s' % ( oid, suffix )
                    self._run('cp %s %s' % ( os.path.join(import_from, filename), import_to ), 'copying')

                    try: portal.manage_delObjects( oid )
                    except: pass

                    x = os.path.join(import_to, filename)
                    portal._importObjectFromFile( x, verify=0, set_owner=0 )
                    logger.info('runSyncPortalTools imported: %s' % x )

        except Exception, msg_error:
            message = str(msg_error)
            IsError = 1
            raise

        transaction.get().commit()

        if not mode:
            logger.info('runSyncPortalTools results: %s' % str(IsError and 'error' or 'successfully'))
        if not mode and REQUEST is not None:
            if not IsError:
                message = 'Syncronization of %s performed successfully' % id
            elif not message:
                message = 'Syncronization of %s performed with error $ $ error' % id
            REQUEST['RESPONSE'].redirect( self.absolute_url( action="sync_portal_form", message=message ) )

        return ( IsError and 1 or 0, [], )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getEmergencyServiceState' )
    def getEmergencyServiceState( self, instance, REQUEST=None ):
        """
            Returns emergency service state
        """
        p = getToolByName( self, 'portal_properties', None )
        current_instance = p.instance_name()
        property = 'emergency_service'

        if current_instance != instance:
            addr = portalConfiguration.getAttribute( attr='remote_portal_addresses', \
                key='anonymous', instance=instance, \
                context=self )
            if not addr:
                return None
            p = xmlrpclib.Server( '%s/%s' % ( addr, 'portal_properties' ) )

        try:
            return p.getProperty( property )
        except:
            return None

    security.declareProtected( CMFCorePermissions.ManagePortal, 'runTurnEmergencyService' )
    def runTurnEmergencyService( self, turn, mode=None, REQUEST=None ):
        """
            Turns on/off emergency service portal mode
        """
        uname = _getAuthenticatedUser(self).getUserName()
        p = getToolByName( self, 'portal_properties', None ).parent()
        property = 'emergency_service'

        logger.info('runTurnEmergencyService turned %s by %s' % ( turn, uname ))

        message = ''
        IsError = 0

        try:
            if p.hasProperty( property ):
                p._updateProperty( property, turn == 'on' and 1 or 0 )
            if not mode:
                IsError, res = self.sync_property( 'runTurnEmergencyService', None, None, 1, turn, 1 )

        except Exception, msg_error:
            message = "%s $ $ error" % str(msg_error)
            IsError = 1

        transaction.get().commit()

        if not mode and REQUEST is not None:
            if not IsError:
                message = 'Emergency service turned %s successfully' % turn
            elif not message:
                message = 'Emergency service turned %s with error $ $ error' % turn
            REQUEST['RESPONSE'].redirect( self.absolute_url( action="sync_portal_form", message=message ) )

        return ( IsError and 1 or 0, [], )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'createHomeFolders' )
    def createHomeFolders( self, mode=None, IsRun=0, create_defaults=1, access='W', REQUEST=None ):
        """
            Checks and creates new and lost member's home folders
        """
        uname = _getAuthenticatedUser(self).getUserName()
        membership = getToolByName( self, 'portal_membership', None )
        catalog = getToolByName( self, 'portal_catalog', None )
        if None in ( membership, catalog, ):
            if not mode:
                REQUEST['RESPONSE'].redirect( self.absolute_url( action="sync_portal_form" ) )
            else:
                return
        portal = self.getPortalObject()
        instance = portal.getId()
        IsRun = int(str(IsRun))

        logger.info('createHomeFolders run by %s, IsRun: %s' % ( uname, IsRun ))

        if not mode:
            message = IsRun and 'Creation of home folders' or 'Check of home folders'
        IsError = 0
        res = []

        try:
            context = portal.storage.members.user_defaults
            defaults = context.objectIds()
            cp = [ context.manage_copyObjects([x]) for x in defaults ]
        except:
            cp = None

        ids = membership.getMemberIds( access )

        created_homes = []
        bad_members = []
        bad_homes = []

        for id in ids:
            if not id: continue
            member = membership.getMemberById( id )
            if member is None:
                bad_members.append( id )
                continue

            IsCreatedHome = 0
            IsCreatedDefaults = 0
            recursive = 0
            idxs = []

            home = member.getHomeFolder()
            if home is None and IsRun:
                home = member.getHomeFolder( create=1 )
                IsCreatedHome = 1
            if home is None:
                bad_homes.append( id )
                continue
            if IsCreatedHome:
                created_homes.append( id )

            if not IsRun: continue

            if not hasattr(home, 'creators') or id not in home.creators:
                setattr( home, 'creators', (id,) )
                idxs.append('Creator')

            if create_defaults and cp is not None:
                home_objects = home.objectIds()
                for n in range(len(defaults)):
                    x = defaults[ n ]
                    if x not in home_objects:
                        home.manage_pasteObjects( cp[n] )
                        IsCreatedDefaults = 1

            if IsCreatedHome or IsCreatedDefaults:
                res = catalog.searchResults( path=home.physical_path()+'%', implements='isContentStorage' )
                for r in res:
                    ob = r.getObject()
                    if ob is None: continue
                    ob.delLocalRoles( userids=[ uname, 'x' ] )
                    if 'allowedRolesAndUsers' not in idxs:
                        idxs.append('allowedRolesAndUsers')
                    else:
                        recursive = 1

            if idxs:
                home.reindexObject( idxs=idxs, recursive=recursive )

        if not mode:
            IsError, res = self.sync_property( 'createHomeFolders', 2, None, 0, 1, IsRun, create_defaults, access )

        transaction.get().commit()

        s = '<b>%s:</b>' % instance
        if created_homes or bad_members or bad_homes:
            if created_homes:
                if bad_members or bad_homes: s += '\n'
                l = len(created_homes)
                s += '_<font_color=green>created_homes'
                if l > 10:
                    s += '('+str(l)+')</font>'
                else:
                    s += '['+','.join(created_homes)+']</font>'
            if bad_members:
                if created_homes or bad_homes: s += '\n'
                s += '_<font_color=blue>bad_members[' % msg('')+','.join(bad_members)+']</font>'
            if bad_homes:
                if created_homes or bad_members: s += '\n'
                l = len(bad_homes)
                s += '_<font_color=red>bad_homes'
                if l > 10:
                    s += '('+str(l)+')</font>'
                else:
                    s += '['+','.join(bad_homes)+']</font>'
        else:
            s += '_<font_color=green>OK</font>'

        #logger.info('createHomeFolders res: %s' % str(s))

        if not mode:
            res.append( s )
            msg = getToolByName( self, 'msg', None )
            if msg is not None:
                for n in range(len(res)):
                    for x in ('created_homes', 'bad_members', 'bad_homes'):
                        res[n] = res[n].replace(x, msg(x))

        if not mode and REQUEST is not None:
            if not IsError:
                message += ' performed successfully'
            elif not message:
                message += ' performed with error $ $ error'
            REQUEST['RESPONSE'].redirect( self.absolute_url( action='sync_portal_form', message=message, \
                params={'create_home_folders' : res} \
            ) )

        return ( IsError and 1 or 0, s )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'createDepartmentFolders' )
    def createDepartmentFolders( self, mode=None, IsRun=0, department=None, editor=None, \
            create_IO_shortcuts=None, set_roles=None, set_postfix=None, \
            REQUEST=None ):
        """
            Checks and creates new and lost department's folders
        """
        if not ( department and editor ):
            if mode or REQUEST is None:
                return ( 1, '' )
            message = 'You should assign department and editor attribute values! $ $ error'
            return REQUEST['RESPONSE'].redirect( self.absolute_url( action='sync_portal_form', message=message, \
                params={'create_department_folders' : []} \
            ) )

        uname = _getAuthenticatedUser(self).getUserName()
        membership = getToolByName( self, 'portal_membership', None )
        catalog = getToolByName( self, 'portal_catalog', None )
        if None in ( membership, catalog, ):
            if not mode:
                REQUEST['RESPONSE'].redirect( self.absolute_url( action="sync_portal_form" ) )
            else:
                return

        portal = self.getPortalObject()
        instance = portal.getId()
        IsRun = int(str(IsRun))

        logger.info('createDepartmentFolders run by %s, IsRun: %s, params: %s' % ( uname, IsRun, \
            str(( department, editor, create_IO_shortcuts, set_roles, set_postfix, ))))

        if not mode:
            message = IsRun and 'Creation of department folders' or ''
        changed_objects = []
        IsError = 0
        res = []

        editors = tuple( editor )
        company = departmentDictionary.getCompanyId( department )

        if IsDefaultCompany( self, company ):
            title = departmentDictionary.getDepartmentTitle( department )
            postfix = departmentDictionary.getDepartmentPostfix( department )

            try:
                group = membership.getGroup( department )
            except: 
                group = None

            author_roles   = [ AuthorRole ]
            editor_roles   = [ EditorRole ]
            writer_roles   = [ WriterRole ]
            workflow_roles = [ ReaderRole, WorkflowChiefRole ]

            editor_members   = membership.getGroupMembers( '_editors_' )
            writer_members   = membership.getGroupMembers( '_SIGN_' )
            workflow_members = membership.getGroupMembers( '_workflow_chiefs_' )

            segments = DefaultSegment( portal, extended=1 )

            for x, extended in segments:
                if x is None: continue
                should_be_created = 0
                IsChanged = 0
                idxs = []

                if hasattr(aq_base(x), company) and not extended:
                    if x[company]._getOb( department, None ) is None:
                        should_be_created = 1
                    segment = x[company]
                else:
                    if x._getOb( department, None ) is None:
                        should_be_created = 1
                    segment = x

                if should_be_created:
                    segment.manage_addHeading( id=department, title=title, set_owner=0 )

                try: ob = segment[ department ]
                except: ob = None

                if ob is None: continue

                if lower(ob.Title()).strip() != lower(title).strip():
                    ob.setTitle( title )
                    idxs.append('Title')
                    IsChanged = 1

                if editor:
                    if not hasattr(ob, 'creators') or ob.creators != editors:
                        setattr( ob, 'creators', editors )
                        idxs.append('Creator')
                        IsChanged = 1

                if set_postfix:
                    if postfix and postfix != ob.getPostfix():
                        ob.setPostfix( postfix )
                        IsChanged = 1

                if set_roles and group is not None:
                    members = membership.getGroupMembers(department)
                    members.sort()

                    #for member_id, role in ob.getLocalRoles():
                    #    if member_id not in members:
                    #        ob.manage_delLocalRoles( (member_id,) )

                    for member_id in members:
                        local_roles = ob.getLocalRoles( member_id )[0]
                        roles = []

                        # we should set only missed roles
                        if not extended:
                            member = membership.getMemberById( member_id )
                            if member is None or not member.getMemberAccessLevel( instance ):
                                roles = None
                            elif member_id in editor_members and ( editors and member_id in editors or not editors ):
                                local_editors = check_role( ob, EditorRole )
                                if not local_editors:
                                    roles.extend( editor_roles )
                                elif member_id not in local_editors:
                                    roles.extend( writer_roles )
                            elif member_id in writer_members:
                                roles.extend( writer_roles )
                            elif not local_roles:
                                roles.extend( author_roles )

                        if roles is None:
                            ob.manage_delLocalRoles( (member_id,) )

                        elif member_id in workflow_members and not check_role( ob, WorkflowChiefRole ):
                            if extended:
                                roles.append( WorkflowChiefRole )
                            else:
                                roles.extend( workflow_roles )

                        # check if role exists
                        if roles:
                            if not filter( lambda r, l=local_roles: r not in l, roles ):
                                continue
                            ob.manage_setLocalRoles( member_id, roles )
                        elif roles is not None:
                            continue

                        idxs.append('allowedRolesAndUsers')
                        IsChanged = 1

                if should_be_created:
                    ob.reindexObject()
                elif idxs:
                    ob.reindexObject( idxs=idxs, recursive=None )

                if should_be_created or IsChanged:
                    changed_objects.append( ob.physical_path() )

            ob = departmentDictionary.getDepartmentFolder( portal, id=department )

            if ob is not None and create_IO_shortcuts:
                path = '/%s/storage/SCR/IO' % instance

                for id, parent, info in ( \
                        ( 'outgoing', 'Iskhodjashhie', ( ' ИСХОДЯЩИЕ', '%s. Исходящая корреспонденция' ) ), \
                        ( 'incoming', 'Vkhodjashhie',  ( ' ВХОДЯЩИЕ',  '%s. Входящая корреспонденция'  ) ), \
                    ):
                    if getattr( aq_base(ob), id, None ) is not None:
                        continue

                    try:
                        IO = portal.unrestrictedTraverse( '%s/%s/%s' % ( path, parent, department ) )
                    except:
                        IO = None

                    if IO is None: continue

                    ob.manage_addProduct['ExpressSuiteTools'].addShortcut( \
                        id=id, 
                        title=info[0], 
                        description=info[1] % title,
                        remote=IO.getUid()
                    )
                    x = ob._getOb( id, None )

                    if x is None: continue

                    if editors:
                        setattr( x, 'creators', editors )
                        x.reindexObject()

        if not mode:
            IsError, res = self.sync_property( 'createDepartmentFolders', 2, None, 0, 1, IsRun, department, editor, \
                create_IO_shortcuts, set_roles, set_postfix )

        transaction.get().commit()

        s = '<b>%s:</b>' % instance
        if changed_objects:
            s += '_<font_color=red>'+','.join(changed_objects)+'</font>'
        else:
            s += '_<font_color=green>OK</font>'

        if not mode and REQUEST is not None:
            if not IsError:
                message += ' performed successfully'
            elif not message:
                message += ' performed with error $ $ error'
            REQUEST['RESPONSE'].redirect( self.absolute_url( action='sync_portal_form', message=message, \
                params={'create_department_folders' : res} \
            ) )

        return ( IsError and 1 or 0, s )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setWorkflowChiefs' )
    def setWorkflowChiefs( self, mode=None, IsRun=0, department=None, member=None, recursive=None, REQUEST=None ):
        """
            Checks and creates new and lost department's workflow chiefs
        """
        if not ( department and member ):
            if mode or REQUEST is None:
                return ( 1, '' )
            message = 'You should assign department and member attribute values! $ $ error'
            return REQUEST['RESPONSE'].redirect( self.absolute_url( action='sync_portal_form', message=message, \
                params={'set_workflow_chiefs' : []} \
            ) )

        uname = _getAuthenticatedUser(self).getUserName()
        membership = getToolByName( self, 'portal_membership', None )
        catalog = getToolByName( self, 'portal_catalog', None )
        if None in ( membership, catalog, ):
            if not mode:
                return REQUEST['RESPONSE'].redirect( self.absolute_url( action="sync_portal_form" ) )
            else:
                return ( 1, '' )

        portal = self.getPortalObject()
        instance = portal.getId()
        IsRun = int(str(IsRun))

        logger.info('setWorkflowChiefs run by %s, IsRun: %s, params: %s' % ( uname, IsRun, \
            str(( department, member, recursive, ))))

        if not mode:
            message = IsRun and 'Assigning workflow chief permissions' or ''
        changed_objects = []
        IsError = 0
        res = []

        departments = catalog.searchResults( path='%/'+department, implements='isContentStorage' )

        for x in departments:
            folder = x.getObject()
            if folder is None: continue
            path = x.getPath()
            IsChanged = 0

            workflow_roles = '/SCR/IO/' in path and [ WorkflowChiefRole ] or [ ReaderRole, WorkflowChiefRole ]
            workflow_chiefs = folder.users_with_local_role( WorkflowChiefRole )

            for x in workflow_chiefs:
                if x in member: continue
                local_roles = folder.get_local_roles_for_userid( x )
                roles = [ role for role in local_roles if role not in workflow_roles ]
                folder.delLocalRoles( userids=[x] )
                if not roles: continue
                folder.manage_setLocalRoles( x, roles )
                IsChanged = 1

            for x in member:
                local_roles = folder.get_local_roles_for_userid( x )
                roles = [ role for role in workflow_roles if role not in local_roles ]
                if not roles: continue
                folder.manage_setLocalRoles( x, workflow_roles )
                IsChanged = 1

            if IsChanged: changed_objects.append( path )

            if IsRun:
                folder.reindexObject( idxs=['allowedRolesAndUsers'], recursive=recursive )

        if not mode:
            IsError, res = self.sync_property( 'setWorkflowChiefs', 2, None, 0, 1, IsRun, department, member, recursive )

        transaction.get().commit()

        s = '<b>%s:</b>' % instance
        if changed_objects:
            s += '_<font_color=red>'+','.join(changed_objects)+'</font>'
        else:
            s += '_<font_color=green>OK</font>'

        #logger.info('setWorkflowChiefs res: %s' % str(s))

        if not mode and REQUEST is not None:
            if not IsError:
                message += ' performed successfully'
            elif not message:
                message += ' performed with error $ $ error'
            REQUEST['RESPONSE'].redirect( self.absolute_url( action='sync_portal_form', message=message, \
                params={'set_workflow_chiefs' : res} \
            ) )

        return ( IsError and 1 or 0, s )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setAccessLevel' )
    def setAccessLevel( self, mode=None, IsRun=0, group=None, instance=None, level=None, REQUEST=None ):
        """
            Sets new access level for given user's group
        """
        if not ( group and instance and level ):
            if mode or REQUEST is None:
                return ( 1, '' )
            message = 'You should select user group, instance and access level attribute values! $ $ error'
            return REQUEST['RESPONSE'].redirect( self.absolute_url( action='sync_portal_form', message=message, \
                params={'set_access_level' : []} \
            ) )

        uname = _getAuthenticatedUser(self).getUserName()
        membership = getToolByName( self, 'portal_membership', None )
        if None in ( membership, ):
            if not mode:
                return REQUEST['RESPONSE'].redirect( self.absolute_url( action="sync_portal_form" ) )
            else:
                return ( 1, '' )

        portal = self.getPortalObject()
        IsRun = int(str(IsRun))
        levels = portalConfiguration.getAccessLevels( simple=1 )

        logger.info('setAccessLevel run by %s, IsRun: %s, params: %s' % ( uname, IsRun, \
            str(( group, instance, level, ))))

        if not mode:
            message = 'Assigning access level for given user group'
        changed_objects = []
        IsError = 0
        res = []

        exclude_users = ( 'admin', )

        for id in membership.getGroupMembers(group):
            if exclude_users and id in exclude_users:
                continue
            member = membership.getMemberById( id )
            if member is None:
                IsError = 1
                continue

            member_access = member.getMemberAccessLevel( id=instance )

            if level in levels:
                if member_access == level: continue
            else:
                if not member_access: continue
                
            mapping = {}
            mapping['instance_%s' % instance] = level in levels and level or None

            if IsRun:
                member.setMemberProperties( mapping )

            changed_objects.append( id )

        res = [ '<br><font_color=blue>%schanged_%s_members</font>' % ( not IsRun and 'should_be_' or '', len(changed_objects) ) ]

        transaction.get().commit()

        if not mode:
            msg = getToolByName( self, 'msg', None )
            if msg is not None:
                for n in range(len(res)):
                    for x in ('should_be_changed', 'changed', 'members'):
                        res[n] = res[n].replace(x, msg(x))

        if not mode and REQUEST is not None:
            if not IsError:
                message += ' performed successfully'
            elif not message:
                message += ' performed with error $ $ error'
            REQUEST['RESPONSE'].redirect( self.absolute_url( action='sync_portal_form', message=message, \
                params={'set_access_level' : res} \
            ) )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'manageImportArchive' )
    def manageImportArchive( self, mode=None, IsApply=0, REQUEST=None, **kw ):
        """
            Performs import archive actions
        """
        uname = _getAuthenticatedUser(self).getUserName()
        portal = self.getPortalObject()

        IsApply = int(str(IsApply))

        message = 'Apply settings'
        IsError = 0
        res = []

        logger.info('manageImportArchive by %s' % uname)

        if IsApply:
            self.setArchiveSchedule( REQUEST, **kw )

        if IsApply:
            self._log('archive', '.')

        if REQUEST is not None:
            if not IsError:
                message += ' performed successfully'
            else:
                message += ' performed with error $ $ error'
            REQUEST['RESPONSE'].redirect( self.absolute_url( action='manage_archive_form', message=message, \
                params={'manage_archive' : res} ) \
            )

        return ( IsError and 1 or 0, [], )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'manageExportArchive' )
    def manageExportArchive( self, mode=None, IsCheck=0, IsRun=0, IsApply=0, REQUEST=None, **kw ):
        """
            Performs export archive actions
        """
        uname = _getAuthenticatedUser(self).getUserName()
        portal = self.getPortalObject()

        IsCheck = int(str(IsCheck))
        IsRun = int(str(IsRun))
        IsApply = int(str(IsApply))

        message = IsRun and 'Run DB archive' or IsApply and 'Apply settings' or 'Check archive'
        IsError = 0
        res = []

        logger.info('manageExportArchive by %s mode %s' % ( uname, message ))

        if IsCheck or IsRun or IsApply:
            self.setArchiveScenario( REQUEST, **kw )

        if IsRun:
            if not IsError and self.IsArchiveScenarioPhaseActivated( 'pack_before' ):
                IsError = self._pack_now()
            if not IsError and self.IsArchiveScenarioPhaseActivated( 'backup' ):
                IsError = self._backup_now()
            if not IsError and self.IsArchiveScenarioPhaseActivated( 'make_DB_copy' ):
                IsError = self._make_DB_copy()

        if IsCheck or IsRun or IsApply:
            self.setArchivePeriod( REQUEST, **kw )
            self.setArchiveDescription( REQUEST, **kw )
            self.setArchiveSelectedCategories( REQUEST, **kw )
            self.setArchiveExpiredOptions( REQUEST, **kw )

        if IsCheck or IsRun:
            if not IsError and self.IsArchiveScenarioPhaseActivated( 'ARC0' ):
                if self.ARC0( IsRun, REQUEST ):
                    message = 'ARC0'
                    IsError = 1
            if not IsError and self.IsArchiveScenarioPhaseActivated( 'ARC1' ):
                if self.ARC1( IsRun, IsForce=self.IsArchiveForce(), REQUEST=REQUEST ):
                    if not self.IsArchiveIgnoreErrors():
                        message = 'ARC1'
                        IsError = 1
            if not IsError and self.IsArchiveScenarioPhaseActivated( 'ARC2' ):
                if self.ARC2( IsRun, REQUEST ):
                    if not self.IsArchiveIgnoreErrors():
                        message = 'ARC2'
                        IsError = 1

        if IsCheck or IsRun:
            if not IsError and self.IsArchiveScenarioPhaseActivated( 'clean_archive' ):
                if self._clean_archive( IsRun ):
                    IsError = not self.IsArchiveIgnoreErrors() and 1 or 0

        if IsRun:
            if not IsError and self.IsArchiveScenarioPhaseActivated( 'pack' ):
                IsError = self._pack_now()
            if not IsError and self.IsArchiveScenarioPhaseActivated( 'export' ):
                IsError = self._export()
            if not IsError and self.IsArchiveScenarioPhaseActivated( 'remove' ):
                IsError = self._remove()

        if IsCheck or IsRun:
            if not IsError and self.IsArchiveScenarioPhaseActivated( 'clean_storage' ):
                if self._clean_storage( IsRun ):
                    IsError = not self.IsArchiveIgnoreErrors() and 1 or 0
                if IsRun:
                    self._remove_shortcuts()

        if IsRun:
            if not IsError and self.IsArchiveScenarioPhaseActivated( 'pack_after' ):
                IsError = self._pack_now()

        if IsCheck or IsRun:
            self._log('archive', '.')

        if REQUEST is not None:
            if not IsError:
                message += ' performed successfully'
            else:
                message += ' performed with error $ $ error'
            REQUEST['RESPONSE'].redirect( self.absolute_url( action='manage_archive_form', message=message, \
                params={'manage_archive' : res} ) \
            )

        return ( IsError and 1 or 0, [], )

    def getArchivePeriod( self ):
        """
            Returns archive archive_period
        """
        now = DateTime()
        default = ( DateTime( now.year(), 1, 1 ), DateTime( now.year(), 12, 31 ) )
        return getattr( self, 'archive_period', None ) or default

    def setArchivePeriod( self, REQUEST=None, **kw ):
        """
            Sets archive archive_period
        """
        _from = get_param('created_from', REQUEST, kw, None).split('.')
        _till = get_param('created_till', REQUEST, kw, None).split('.')
        self.archive_period = ( \
            DateTime(int(_from[2]), int(_from[1]), int(_from[0])), \
            DateTime(int(_till[2]), int(_till[1]), int(_till[0])), )
        self._p_changed = 1

    def getArchiveSelectedCategories( self ):
        """
            Returns selected archive categories
        """
        return getattr( self, 'archive_selected_categories', [] )

    def setArchiveSelectedCategories( self, REQUEST=None, **kw ):
        """
            Sets selected archive categories
        """
        self.archive_selected_categories = get_param('selected_categories', REQUEST, kw, [])
        self._p_changed = 1

    def getArchiveExpiredOptions( self ):
        """
            Returns expired archive category options
        """
        return getattr( self, 'archive_expired_options', {} )

    def setArchiveExpiredOptions( self, REQUEST=None, **kw ):
        """
            Sets expired archive category options
        """
        metadata = getToolByName( self, 'portal_metadata', None )
        if metadata is None:
            return

        categories = metadata.getCategories()
        archive_expired_options = {}
        for x in categories:
            id = x.getId()
            try: period = int(get_param('%s_period' % id, REQUEST, kw, None))
            except: period = -1
            expired_attr = get_param('%s_expired_attr' % id, REQUEST, kw, '')
            try: units = int(get_param('%s_units' % id, REQUEST, kw, None))
            except: units = 30
            try: default = int(get_param('%s_default' % id, REQUEST, kw, None))
            except: default = 1
            archive_expired_options[id] = ( period, expired_attr, units, default )

        self.archive_expired_options = archive_expired_options
        self._p_changed = 1

    def getArchiveDescription( self, items=None ):
        """
            Returns archive description
        """
        instance = self.getPortalObject().getId()
        msg = getToolByName( self, 'msg' )

        x = {}
        a = getattr( self, 'archive_description', None ) or {}
        x['instance'] = ( 1, 'Instance', 20, a.get('instance') or 'archive', 'text' )
        x['export_path'] = ( 0, 'Export to the server directory', 100, a.get('export_path') or '', 'text', '', '' )
        x['name'] = ( 10, 'ID', 20, a.get('name') or DateTime().strftime( '%Y-%m' ), 'text' )
        x['title'] = ( 20, 'Title', 100, a.get('title') or x['name'][3], 'text' )
        x['description'] = ( 30, 'Description', 100, a.get('description') or '%s %s %s' % ( msg('Company Archive'), DateTime().strftime( '%Y' ), msg('y.') ), 'text' )
        x['create_defaults'] = ( 40, 'Create defaults', 3, int(a.get('create_defaults') or 0), 'checkbox' )
        x['include_companies'] = ( 50, 'Include companies', 100, a.get('include_companies') or '', 'text' )
        x['check_scheduler_queue'] = ( 60, 'Check scheduler queue', 3, int(a.get('check_scheduler_queue') or 0), 'checkbox' )
        x['apply_threading'] = ( 61, 'Apply threading', 3, int(a.get('apply_threading') or 0), 'checkbox' )
        x['commit_every'] = ( 62, 'Commit every', 10, int(a.get('commit_every', 10)), 'text', '', 'text-align:center' )
        x['threshold'] = ( 63, 'Threshold', 10, int(a.get('threshold', 5000)), 'text', '', 'text-align:center' )
        x['reindex'] = ( 70, 'Reindex', 3, int(a.get('reindex') or 0), 'checkbox' )
        x['path'] = ( 80, 'Achive catalog', 100, a.get('path') or '/%s/storage/arc' % instance, 'text' )
        x['source'] = ( 90, 'Source', 100, a.get('source') or '/%s/storage/system/structure/source_defaults' % instance, 'text' )
        x['editor_members'] = ( 100, 'Editor members', 20, a.get('editor_members') or '_editors_', 'text' )
        x['workflow_members'] = ( 110, 'Workflow members', 20, a.get('workflow_members') or '_workflow_chiefs_', 'text' )

        if items:
            res = [ ( x[key][0], key, x[key][1], x[key][2], x[key][3], x[key][4], \
                      len(x[key]) > 5 and x[key][5] or '',          # comment
                      len(x[key]) > 6 and x[key][6] or '',          # style
                      len(x[key]) > 7 and x[key][7] and 1 or 0,     # disabled
                      ) \
                      for key in x.keys() ]
            res.sort()
        else:
            res = {}
            for key in x.keys():
                res[key] = x[key][3]
        return res

    def setArchiveDescription( self, REQUEST=None, **kw ):
        """
            Sets archive description
        """
        x = {}
        archive_description = self.getArchiveDescription()

        for key in archive_description.keys():
            x[key] = get_param(key, REQUEST, kw, None) # REQUEST.get(key)

        self.archive_description = x
        self._p_changed = 1

    def getArchiveScenario( self ):
        """
            Returns archive scenario
        """
        x = []
        default_state = () # ( 'pack', 'backup', 'ARC0', 'ARC1', 'ARC2', 'export', )
        x = ( \
            { 
                'id'    : 'pack_before', 
                'title' : 'Pack database', 
                'state' : ( self.IsArchiveScenarioPhaseActivated('pack_before') or 'pack_before' in default_state ) and 1 or 0, 
            }, 
            { 
                'id'    : 'backup', 
                'title' : 'Backup database', 
                'state' : ( self.IsArchiveScenarioPhaseActivated('backup') or 'backup' in default_state ) and 1 or 0, 
            },
            { 
                'id'    : 'make_DB_copy', 
                'title' : 'Make database file copy', 
                'state' : ( self.IsArchiveScenarioPhaseActivated('make_DB_copy') or 'make_DB_copy' in default_state ) and 1 or 0, 
            },
            { 
                'id'    : 'ARC0', 
                'title' : '[ARC0] Create archive export folders', 
                'state' : ( self.IsArchiveScenarioPhaseActivated('ARC0') or 'ARC0' in default_state ) and 1 or 0, 
            },
            { 
                'id'    : 'ARC1', 
                'title' : '[ARC1] Perform workflow archive transition', 
                'state' : ( self.IsArchiveScenarioPhaseActivated('ARC1') or 'ARC1' in default_state ) and 1 or 0, 
            },
            { 
                'id'    : 'ARC2', 
                'title' : '[ARC2] Validate object attributes', 
                'state' : ( self.IsArchiveScenarioPhaseActivated('ARC2') or 'ARC2' in default_state ) and 1 or 0, 
            },
            { 
                'id'    : 'clean_archive', 
                'title' : 'Remove empty folders inside archive', 
                'state' : ( self.IsArchiveScenarioPhaseActivated('clean_archive') or 'clean_archive' in default_state ) and 1 or 0, 
            },
            { 
                'id'    : 'pack', 
                'title' : 'Pack database', 
                'state' : ( self.IsArchiveScenarioPhaseActivated('pack') or 'pack' in default_state ) and 1 or 0, 
            }, 
            { 
                'id'    : 'export', 
                'title' : 'Export archive folder', 
                'state' : ( self.IsArchiveScenarioPhaseActivated('export') or 'export' in default_state ) and 1 or 0, 
            },
            { 
                'id'    : 'remove', 
                'title' : 'Remove all', 
                'state' : ( self.IsArchiveScenarioPhaseActivated('remove') or 'remove' in default_state ) and 1 or 0, 
            },
            { 
                'id'    : 'clean_storage', 
                'title' : 'Remove empty folders inside storage', 
                'state' : ( self.IsArchiveScenarioPhaseActivated('clean_storage') or 'clean_storage' in default_state ) and 1 or 0, 
            },
            { 
                'id'    : 'pack_after', 
                'title' : 'Pack database', 
                'state' : ( self.IsArchiveScenarioPhaseActivated('pack_after') or 'pack_after' in default_state ) and 1 or 0, 
            }, 
        )
        return x

    def setArchiveScenario( self, REQUEST=None, **kw ):
        """
            Sets archive scenario
        """
        IsChanged = 0
        archive_scenario = getattr( self, 'archive_scenario', None ) or []

        for phase in self.getArchiveScenario():
            id = phase['id']
            state = phase['state']
            x = get_param(id, REQUEST, kw, None)
            if x == state:
                continue
            if x and id not in archive_scenario:
                archive_scenario.append(id)
                IsChanged = 1
            if not x and id in archive_scenario:
                archive_scenario.remove(id)
                IsChanged = 1
        if IsChanged:
            setattr( self, 'archive_scenario', archive_scenario )
            self._p_changed = 1

        self.setArchiveMode( REQUEST, **kw )

    def getArchiveSchedule( self, items=None ):
        """
            Returns archive import scheduler items
        """
        instance = self.getPortalObject().getId()
        msg = getToolByName( self, 'msg' )

        x = {}
        a = getattr( self, 'archive_schedule', None ) or {}
        x['path'] = ( 10, 'Achive catalog', 100, a.get('path') or '/%s/storage/arc' % instance, 'text' )
        x['import_path'] = ( 0, 'Import from the server directory', 100, a.get('import_path') or '', 'text', '', '' )
        x['import_timeout'] = ( 20, 'Schedule timeout', 10, int(a.get('import_timeout', 10)), 'text', '0 is disabled', 'text-align:center' )
        x['apply_threading'] = ( 30, 'Apply threading', 3, int(a.get('apply_threading') or 0), 'checkbox' )
        x['lock_catalog'] = ( 31, 'Lock catalog', 3, int(a.get('lock_catalog') or 0), 'checkbox' )

        import_schedule_id = getattr( self, '_import_schedule_id', None )
        if import_schedule_id:
            scheduler = getToolByName( self, 'portal_scheduler', None )
            if scheduler is None or not scheduler.getScheduleElement( import_schedule_id ):
                self._import_schedule_id = import_schedule_id = None
                self._p_changed = 1

        x['import_schedule_id'] = ( 40, 'Import schedule id', 50, \
            import_schedule_id and '%s (%s)' % ( msg('enabled'), import_schedule_id ) or msg('disabled'),
            'text', '',
            import_schedule_id and 'color:green' or 'color:red', 1
            )

        if items:
            res = [ ( x[key][0], key, x[key][1], x[key][2], x[key][3], x[key][4], \
                      len(x[key]) > 5 and x[key][5] or '',          # comment
                      len(x[key]) > 6 and x[key][6] or '',          # style
                      len(x[key]) > 7 and x[key][7] and 1 or 0,     # disabled
                      ) \
                      for key in x.keys() ]
            res.sort()
        else:
            res = {}
            for key in x.keys():
                res[key] = x[key][3]
        return res

    def setArchiveSchedule( self, REQUEST=None, **kw ):
        """
            Sets archive import scheduler items
        """
        x = {}
        archive_schedule = self.getArchiveSchedule()

        for key in archive_schedule.keys():
            x[key] = get_param(key, REQUEST, kw, None)
            if key == 'import_timeout':
                scheduler = getToolByName( self, 'portal_scheduler', None )
                msg = getToolByName( self, 'msg', None )
                if None in ( scheduler, msg, ):
                    continue
                value = int(x[key] or 0)

                if value and int(archive_schedule.get(key) or 0) == value and getattr( self, '_import_schedule_id', None ) and \
                    scheduler.getScheduleElement( self._import_schedule_id ):
                    pass

                elif value > 0:
                    frequency = value * 60
                    date = DateTime() + float(frequency) / 86400
                    temporal_expr = UniformIntervalTE( frequency, start_date=date )

                    self._import_schedule_id = scheduler.addScheduleElement( self.ImportToArchive
                        , title="[Periodical Event] %s" % msg('Import to archive')
                        , temporal_expr=temporal_expr 
                        , prefix='I'
                        )

                elif getattr( self, '_import_schedule_id', None ):
                    scheduler.delScheduleElement( [ self._import_schedule_id ] )
                    self._import_schedule_id = None

        self.archive_schedule = x
        self._p_changed = 1

    def getArchiveCategories( self ):
        """
            Returns category ids marked to be archived
        """
        res = []
        metadata = getToolByName( self, 'portal_metadata', None )
        if metadata is None:
            return res

        categories = metadata.getCategories()
        categories.sort( lambda x, y: cmp(x.Title(), y.Title()) )
        archive_selected_categories = self.getArchiveSelectedCategories()
        archive_expired_options = self.getArchiveExpiredOptions()

        for x in categories:
            id = x.getId()
            category = metadata.getCategoryById( id )
            if not category: continue
            attrs_expired = [ attr_id for attr_id in category.getAttributeDefinitionIds() \
                              if attr_id.lower().endswith('expired') ]
            if not archive_expired_options.has_key(id):
                archive_expired_options[id] = ( -1, attrs_expired and attrs_expired[0] or '', 30, 1 )

            res.append( { 'id'              : id,
                          'title'           : x.Title(),
                          'selected'        : id in archive_selected_categories and 1 or 0,
                          'url'             : x.absolute_url(),
                          'period'          : archive_expired_options[id][0],
                          'expired_attr'    : archive_expired_options[id][1],
                          'units'           : archive_expired_options[id][2],
                          'default'         : archive_expired_options[id][3],
                        }
                      )
        return res

    def setArchiveMode( self, REQUEST=None, **kw ):
        for key in ('force', 'ignore_errors', 'trace',):
            setattr(self, 'archive_'+key, get_param(key, REQUEST, kw, None))
        self._p_changed = 1

    def IsArchiveScenarioPhaseActivated( self, id ):
        return id in getattr( self, 'archive_scenario', [] ) and 1 or 0

    def IsArchiveImportScheduleTaskActivated( self ):
        return getattr( self, '_import_schedule_id', None ) and 1 or 0

    def IsArchiveImportRunning( self ):
        return getattr( self, '_import_running', None ) and 1 or 0

    def IsArchiveForce( self ):
        return getattr( self, 'archive_force', None )

    def IsArchiveIgnoreErrors( self ):
        return getattr( self, 'archive_ignore_errors', None )

    def IsArchiveTrace( self ):
        return getattr( self, 'archive_trace', None )

    def _pack_now( self, **kw ):
        """
            Pack DB
        """
        backupFSRoot, url = self._getBackupFSRoot()
        code = None
        if backupFSRoot is not None:
            self._log('archive', message='Pack DB')
            x = backupFSRoot.editProperties( url, {'pack_now' : 1} )
            message = 'OK'
            if x != 'Database have been packed':
                message = x
                code = 1
            self._log('archive', message=message )
        else:
            self._log('archive', message='backupFSRoot is None' )
        return code

    def _backup_now( self, **kw ):
        """
            Backup DB
        """
        backupFSRoot, url = self._getBackupFSRoot()
        code = None
        if backupFSRoot is not None:
            self._log('archive', message='Backup DB')
            x = backupFSRoot.editProperties( url, {'backup_now' : 1} )
            message = 'OK'
            if x != 'Backup copy has been created':
                message = x
                code = 1
            self._log('archive', message=message )
        else:
            self._log('archive', message='backupFSRoot is None' )
        return code

    def _make_DB_copy( self ):
        """
            Creates a copy of DB file storage
        """
        filename = os.path.join(CLIENT_HOME, 'Data.fs')
        now = DateTime().strftime('%Y%m%d')
        _to = os.path.join(INSTANCE_HOME, 'backup', '%s-A' % now)

        self._log('archive', message="Make a copy of %s to %s" % ( filename, _to ))

        try:
            code = self._run('mkdir %s' % _to, 'creating backup folder')
        except: pass

        IsError = self._run('cp %s %s' % ( filename, _to ), 'copying')

        if IsError:
            self._log('archive', message='Error [%s]' % str(IsError) )
        else:
            self._log('archive', "OK")
        
        return IsError

    def _safety_moving( self, _from, _to, filename, no_safe=None ):
        """
            Performs safety moving of file
        """
        if not os.access(_to, os.F_OK|os.W_OK):
            self._run('mkdir %s' % _to, 'creating destination folder')

        if not no_safe:
            x_safe = os.path.join(_to, '-0-')
            if not os.access(x_safe, os.F_OK|os.W_OK):
                self._run('mkdir %s' % x_safe, 'creating safe folder')
            self._run( 'mv %s %s' % ( os.path.join(_from, filename), x_safe ), 'safety moving' )
        else:
            x_safe = _from

        self._run( 'mv %s %s' % ( os.path.join(x_safe, filename), _to ), 'moving' )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'ARC0' )
    def ARC0( self, IsRun=None, REQUEST=None ):
        """
            Phase 0. Creates archive export folders
        """
        if not IsRun:
            return 0

        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return 1

        uname = _getAuthenticatedUser(self).getUserName()
        x = self.getArchiveDescription()

        archive_name = x['name']
        archive_title = x['title']
        archive_description = x['description']
        create_defaults = x['create_defaults']
        threshold = x['threshold']
        include_companies = [ c.strip() for c in x['include_companies'].split(',') ]
        reindex = x['reindex']

        author_roles   = [ AuthorRole ]
        editor_roles   = [ EditorRole ]
        writer_roles   = [ WriterRole ]
        workflow_roles = [ ReaderRole, WorkflowChiefRole ]

        instance = self.getPortalObject().getId()
        path = x['path']

        try:
            context = self.unrestrictedTraverse( path )
        except:
            return 1

        if IsRun:
            self._log('archive', message="= ARC-0. STARTED.  Path: %s, run by %s" % ( path, uname ))

        try:
            source = context.unrestrictedTraverse( x['source'] )
            defaults = source.objectIds()
            cp = [ source.manage_copyObjects( [ item ] ) for item in defaults ]
        except:
            cp = None

        companies = departmentDictionary.listCompanies()

        editor_members = membership.getGroupMembers( x['editor_members'] )
        workflow_members = membership.getGroupMembers( x['workflow_members'] )

        r_total_objects = 0
        r_created = 0
        R_C_ERRORS = []
        R_D_ERRORS = []
        IsCreated = 0
        IsBreak = 0
        IsError = 0

        _created_objects = []

        archive_path = '%s/%s' % ( path, archive_name )
        context, IsCreated = IsFolderExist( context, archive_name, archive_title, archive_path, 1 )
        if context is not None and archive_description and IsCreated:
            context.setDescription( archive_description )
            context.manage_setLocalGroupRoles( 'all_users', author_roles )

        if context is not None and IsRun and reindex:
            context.reindexObject()

        for company in companies:
            company_id = company['id']
            if not company_id or ( include_companies and not company_id in include_companies ):
                continue

            company_title = departmentDictionary.getCompanyTitle( id=company_id, name=1 )
            company_description = company['title']
            company_path = "%s/%s" % ( archive_path, company_id )

            company_folder, IsCreated = IsFolderExist( context, company_id, company_title, company_path, IsRun )
            if company_folder is None:
                R_C_ERRORS.append( company_id )
                continue

            if IsCreated:
                company_folder.setDescription( company_description )
                setattr( company_folder, 'creators', (uname,) )
                _created_objects.append( company_folder.relative_url() )
                r_created += 1

            try: company_group = membership.getGroup( company_id )
            except: company_group = None

            if IsRun and IsCreated:
                if company_group is not None:
                    company_folder.manage_setLocalGroupRoles( company_id, author_roles )
                self._log('archive', message="= ARC-0. Archive of company %s created" % company_id )

            for department in departmentDictionary.listDepartments( company_id ):
                r_total_objects += 1

                department_id = department['id']
                department_title = department['title']
                department_path = "%s/%s/%s" % ( archive_path, company_id, department_id )

                department_folder, IsCreated = IsFolderExist( company_folder, department_id, department_title, department_path, IsRun )
                if department_folder is None:
                    R_D_ERRORS.append( department_id )
                    continue

                if IsCreated:
                    _created_objects.append( department_folder.relative_url() )
                    r_created += 1

                if not IsRun: continue

                if create_defaults and cp is not None:
                    department_objects = department_folder.objectIds()
                    for n in range(len(defaults)):
                        x = defaults[ n ]
                        if x not in department_objects:
                            department_folder.manage_pasteObjects( cp[ n ] )

                try: department_group = membership.getGroup( department_id )
                except: department_group = None

                if IsCreated and department_group is not None:
                    department_folder.manage_setLocalGroupRoles( department_id, author_roles )
                    members = list(membership.getGroupMembers( department_id ))
                    members.sort()

                    for member in members:
                        member_roles = []
                        if member in editor_members:
                            if not check_role( department_folder, EditorRole ):
                                member_roles.extend( editor_roles )
                                setattr( department_folder, 'creators', (member,) )
                            else:
                                member_roles.extend( writer_roles )
                        elif member in workflow_members and not check_role( department_folder, WorkflowChiefRole ):
                            member_roles.extend( workflow_roles )
                        if len(member_roles) > 0:
                            if IsRun:
                                department_folder.manage_setLocalRoles( member, member_roles )

                if reindex:
                    department_folder.reindexObject()

                if IsCreated:
                    self._log('archive', message="= ARC-0. Archive of department %s created" % department_id )

        del companies

        if IsRun:
            transaction.get().commit()

        if IsRun:
            self._log('archive', message='= ARC-0. FINISHED.%s' % ( R_C_ERRORS or R_D_ERRORS and ' Errors: %s-%s' % ( \
                R_C_ERRORS, R_D_ERRORS ) or ''))

        del _created_objects

        return ( R_C_ERRORS or R_D_ERRORS ) and 1 or 0

    security.declareProtected( CMFCorePermissions.ManagePortal, 'ARC1' )
    def ARC1( self, IsRun=None, IsForce=None, REQUEST=None ):
        """
            Phase 1. Performs workflow archive transition
        """
        catalog = getToolByName( self, 'portal_catalog', None )
        metadata = getToolByName( self, 'portal_metadata', None )
        workflow = getToolByName( self, 'portal_workflow', None )
        if None in ( catalog, metadata, workflow, ):
            return 1
        adapter = getattr( metadata, 'taskTemplateContainerAdapter', None )
        if adapter is None:
            return 1

        uname = _getAuthenticatedUser(self).getUserName()
        x = self.getArchiveDescription()
        start_date, end_date = self.getArchivePeriod()

        exclude_states = ( 'OnStorage', 'OnRun', 'OnView', 'OnRegistration', 'OnSined', 'OnSign', 'OnSending', 'evolutive', )
        ToArchive = 'ToArchive'
        template_id = 'move_%s' % ToArchive
        archive_path = x['path']
        archive_name = x['name']
        check_scheduler_queue = x['check_scheduler_queue']
        apply_threading = x['apply_threading']
        commit_every = x['commit_every']
        threshold = x['threshold']

        expired_options = self.getArchiveExpiredOptions()
        category_ids = [ id for id in self.getArchiveSelectedCategories() if expired_options.has_key(id) ]

        instance = self.getPortalObject().getId()
        path = IsRun and '%s/%s' % ( archive_path, archive_name ) or '/%s/storage' % instance

        try:
            context = self.unrestrictedTraverse( path )
        except:
            return 1

        _title = context.Title()
        _uid = context.getUid()
        _URL = context.absolute_url()

        self._log('archive', message="= ARC-1. STARTED.  Period: %s - %s. Path: %s, Threshold: %s, run by %s" % ( \
            start_date, end_date, path, threshold, uname ))

        now = DateTime()

        r_total_objects = 0
        r_archived = 0
        r_invalid = 0
        r_commited = 0
        r_finalized_tasks = 0
        R_ERRORS = 0
        R_BAD_COMMIT = 0
        reindexed_objects = []
        archived_objects = {}
        invalid_objects = []
        task_definitions = {}
        finalized_tasks = []
        folders = []
        IsBreak = 0
        finalize_errors = 0
        IsError = 0
        i = 0
        r_successful_commit = 0

        for id in category_ids:
            archived_objects[id] = 0

            if IsRun:
                task_definitions[id] = adapter.getTaskDefinitionById( id, template_id, '1' )
                request = task_definitions[id].copy()
                request['dest_folder_title'] = _title
                request['dest_folder_uid'] = _uid
                request['dest_folder_URL'] = _URL
                request['template_id'] = template_id
                request['id_task_definition'] = '1'

                adapter.makeTaskDefinitionActionByRequest( id, 'change_task_definition', request )

                self._log('archive', "= ARC-1. Category: %s %s" % ( id, expired_options[id] ))

        def finalizeTasks( followup=None, IsRun=None ):
            if followup is None:
                return
            for id, task in followup.objectItems():
                if task is None:
                    continue
                finalize_schedule_id = task._finalize_schedule_id
                if finalize_schedule_id is not None and task.hasAutoFinalized() and not task.isFinalized():
                    if IsRun:
                        task.Finalize( result_code='success' )
                    finalized_tasks.append( { 'schedule_id' : finalize_schedule_id, 'task_id' : id, 'isFinalized' : task.isFinalized() } )
            return

        query = {}
        query['path'] = { 'query' : archive_path+'%', 'operator' : 'NOT' }

        total_objects = catalog.countResults( REQUEST=None, implements='isHTMLDocument', **query )

        if not IsForce:
            query['created'] = { 'query' : ( start_date, end_date ), 'range' : 'min:max' }

        sort_limit = IsRun and 1000 or int(threshold)

        while threshold > r_total_objects:
            IsNotResults = 1
            self._log('archive', "= ARC-1. Searching...")

            for cat_id in category_ids:
                if IsBreak: break

                query['category'] = cat_id

                res = catalog.searchResults( implements='isHTMLDocument', sort_on='created', sort_limit=sort_limit, **query )

                for r in res:
                    if r_total_objects >= threshold:
                        IsBreak = 1
                        break
                    object_path = r.getPath()
                    if object_path in reindexed_objects:
                        continue
                    if object_path.find('/storage/system') > -1:
                        continue
                    try:
                        obj = r.getObject()
                    except:
                        obj = None
                    if obj is None:
                        if object_path not in invalid_objects:
                            self._log('archive', "= ARC-1. Invalid [Object is None]: %s" % object_path)
                            invalid_objects.append(object_path)
                            r_invalid += 1
                        continue
                    category = obj.getCategory()
                    if category is None:
                        if object_path not in invalid_objects:
                            self._log('archive', "= ARC-1. Invalid [Category is None]: %s %s" % ( cat_id, obj.relative_url() ))
                            invalid_objects.append(object_path)
                            r_invalid += 1
                        continue
                    object_state = workflow.getInfoFor( obj, 'state', None )
                    object_date = DateTime( obj.CreationDate() )
                    if object_state in exclude_states or object_date < start_date or object_date > end_date:
                        continue
                    object_id = obj.getId()
                    object_title = obj.Title()
                    ti = None
                    try:
                        wf = category.__of__(obj).getWorkflow()
                        states = wf.states
                        ti = states[object_state].getTransitions()
                    except:
                        self._log('archive', "= ARC-1. Invalid [Bad workflow]: %s, Transitions: %s" % ( object_path, ti ))
                        r_invalid += 1
                        continue
                    if not ( ToArchive in ti ):
                        continue

                    try:
                        period, attr_name, units, default_value = expired_options[cat_id]
                    except:
                        units = None

                    if not units:
                        continue
                    elif IsForce:
                        if object_date < now - ( default_value * units ):
                            expired = now
                        else:
                            expired = now
                    elif period == -1 and attr_name:
                        attr_value = int(obj.getCategoryAttribute(attr_name) or 0)
                        if not attr_value or attr_value <= 0:
                            attr_value = default_value
                        expired = now - ( attr_value * units )
                    elif period > 0:
                        expired = now - ( period * units )
                    else:
                        continue

                    if not ( object_date < expired ):
                        continue

                    r_total_objects += 1

                    if apply_threading: interrupt_thread( context, force=1 )

                    if IsRun and check_scheduler_queue:
                        followup = getattr( obj, 'followup', None )
                        try:
                            finalizeTasks( followup, IsRun )
                        except:
                            self._log('archive', "= ARC-1[ ERROR ] Finalize: %s" % object_path)
                            finalize_errors += 1

                    if IsRun:
                        archive_date = DateTime()
                        uid = obj.getUid()

                        storage_url = get_relative_url(obj, instance)
                        setattr( obj, 'storage_url', storage_url )
                        obj._p_changed = 1

                        try:
                            x = workflow.doActionFor( obj, ToArchive, comment='%s exported to archive by system process' % str(archive_date) )
                        except:
                            self._log('archive', "= ARC-1[ ERROR ] Transition: %s" % object_path)
                            R_ERRORS += 1
                            continue

                        r_archived += 1
                    else:
                        reindexed_objects.append(object_path)

                    if self.IsArchiveTrace():
                        self._log('archive', "... %s" % object_path)

                    archived_objects[cat_id] += 1
                    IsNotResults = 0

                    if IsRun and commit_every > 0 and divmod( r_total_objects, commit_every )[1] == 0:
                        try:
                            transaction.get().commit()
                            r_commited += commit_every
                            r_successful_commit += 1
                            IsError = 0
                        except:
                            R_BAD_COMMIT += 1
                            IsError = 1

                        self._log('archive', "= ARC-1. %s: %s %s %s %s %s %s %s" % ( 
                            IsError and 'Bad commit' or 'Commit',
                            r_total_objects,
                            r_commited,
                            commit_every,
                            len(finalized_tasks) - r_finalized_tasks,
                            r_invalid,
                            R_ERRORS,
                            r_successful_commit
                            )
                        )

                    r_finalized_tasks = len(finalized_tasks)

                if apply_threading: interrupt_thread( context, force=1 )

            if IsNotResults:
                i += 1

            if IsBreak or IsNotResults and ( sort_limit > total_objects or i >= 3 ):
                break

            if IsNotResults:
                sort_limit = sort_limit * 10

        del res

        if IsRun:
            for id in category_ids:
                request = task_definitions[id].copy()
                request['template_id'] = template_id
                request['id_task_definition'] = '1'

                adapter.makeTaskDefinitionActionByRequest( id, 'change_task_definition', request )

            transaction.get().commit()
            r_successful_commit += 1
        else:
            r_reindexed = len(reindexed_objects)
            del reindexed_objects

        for id in archived_objects.keys():
            self._log('archive', "= ARC-1. Category: %s, archived objects: %s" % ( id, archived_objects[id] ))

        if IsRun:
            self._log('archive', "= ARC-1. FINISHED. Results (total objects, archived, commited, finalized_tasks, invalid, errors, successful commit, BAD_COMMIT): %s %s %s %s %s %s %s %s" % ( \
                r_total_objects, 
                r_archived,
                r_commited,
                r_finalized_tasks,
                r_invalid,
                R_ERRORS,
                r_successful_commit,
                R_BAD_COMMIT
                )
            )

            if finalized_tasks:
                self._log('archive', "= ARC-1. Finalized tasks: %s" % finalized_tasks)
        else:
            self._log('archive', "= ARC-1. FINISHED. Checked (total objects, invalid, errors): %s %s %s" % ( \
                r_total_objects, 
                r_invalid,
                R_ERRORS,
                )
            )

        del archived_objects, invalid_objects, folders

        return R_ERRORS

    security.declareProtected( CMFCorePermissions.ManagePortal, 'ARC2' )
    def ARC2( self, IsRun=None, REQUEST=None ):
        """
            Phase 2. Validate object attributes
        """
        catalog = getToolByName( self, 'portal_catalog', None )
        workflow = getToolByName( self, 'portal_workflow', None )
        links = getToolByName( self, 'portal_links', None )
        metadata = getToolByName( self, 'portal_metadata', None )
        if None in ( catalog, workflow, links, metadata ):
            return 1

        uname = _getAuthenticatedUser(self).getUserName()
        x = self.getArchiveDescription()

        check_states = ( 'OnArchive', )
        archive_instance = x['instance']
        archive_name = x['name']
        archive_location = None
        apply_threading = x['apply_threading']
        commit_every = x['commit_every']
        threshold = x['threshold']

        instance = self.getPortalObject().getId()
        path = '%s/%s' % ( x['path'], archive_name )

        try:
            context = self.unrestrictedTraverse( path )
        except:
            return 0

        self._log('archive', message="= ARC-2. STARTED.  Threshold: %s, run by %s" % ( \
            threshold, uname ))

        now = DateTime()

        res = context.portal_catalog.searchResults( path=path+'%', implements='isContentStorage', sort_on='path', sort_limit=10000 )
        r_total_folders = len(res)-1

        r_total_objects = 0
        r_archived = 0
        r_invalid = 0
        r_entries = 0
        r_commited = 0
        R_ERRORS = 0
        R_BAD_COMMIT = 0
        folders = []
        check_links = []
        IsBreak = 0
        IsError = 0
        i = 0
        r_successful_commit = 0

        bad_entries = []
        bad_links = []

        def getEntry( obj ):
            registry = None
            for reg_id, registry_uids in obj.registry_data.items():
                registry_uid = registry_uids[0]
                registry = context.portal_catalog.unrestrictedGetObjectByUid( registry_uid )
                rnum = reg_id
                break
            if registry is None:
                return None
            entries = rnum and registry.searchRegistryEntries( ID=rnum )
            if not entries:
                sid = registry.getSIDById( rnum )
                number = str(int(registry.getNumberBySID( sid )))
                entries = number and registry.searchRegistryEntries( ID=number )
            if len(entries) > 0:
                entry = entries[0].getObject()
                if entry.get('ID') == rnum:
                    return entry
                else:
                    entry.reindexObject()
            for entry in registry.objectValues():
                if entry.get('ID') == rnum:
                    return entry
            return None

        def check_link( values, uid ):
            global bad_links
            for x in values:
                if not x.has_key('uid'):
                    bad_links.append( x )
                elif x['uid'] == uid:
                    return 1
            return 0

        for r in res:
            if IsBreak: break

            folder = r.getObject()
            if folder is None: continue

            folder_path = folder.physical_path()
            folders.append( folder_path )
            objects = sort_objects( folder.objectValues() )

            for obj in objects:
                if r_total_objects >= threshold:
                    IsBreak = 1
                    break
                i += 1
                if obj is None:
                    self._log('archive', "= ARC-2. Invalid [Object is None]")
                    r_invalid += 1
                    continue
                object_path = obj.relative_url()
                cat_id = obj.Category()
                category = metadata.getCategoryById( cat_id )
                if category is None:
                    self._log('archive', "= ARC-2. Invalid [Category is None]: %s %s" % ( cat_id, object_path ))
                    r_invalid += 1
                    continue
                object_title = obj.Title()
                object_state = workflow.getInfoFor( obj, 'state', None )
                uid = obj.getUid()
                if not object_state in check_states or hasattr( obj, 'archive_url' ):
                    continue

                r_total_objects += 1

                archive_date = DateTime()
                archive_url = get_relative_url( obj, instance )

                if IsRun:
                    remote_links = []
                    links_from = links.searchLinks( source_uid=uid )

                    if links_from:
                        for x in links_from:
                            link = x.getObject()
                            if link is None:
                                continue
                            link_id = link.getId()
                            destination = link.getDestinationObject( version=0 )
                            d_uid = destination.getUid()
                            if destination is None or destination.relative_url().find('favorites') > 0:
                                continue

                            _to = getattr( destination, 'remote_links', [] )
                            if check_link( _to, uid ):
                                continue

                            _to.append( { 'uid' : uid, 'url' :  archive_url, 'title' : object_title } )
                            setattr( destination, 'remote_links', _to )
                            destination._p_changed = 1

                            if check_link( remote_links, d_uid ):
                                continue
                            remote_links.append( { 'uid'   : d_uid, \
                                                   'url'   : get_relative_url( destination ), \
                                                   'title' : destination.Title() } )

                    links_to = links.searchLinks( dest_uid=uid )

                    if links_to:
                        for x in links_to:
                            link = x.getObject()
                            if link is None:
                                continue
                            link_id = link.getId()
                            source = link.getSourceObject( version=0 )
                            s_uid = source.getUid()
                            if source is None or source.relative_url().find('favorites') > 0:
                                continue

                            _from = getattr( source, 'remote_links', [] )
                            if check_link( _from, uid ):
                                continue

                            _from.append( { 'uid' : uid, 'url' :  archive_url, 'title' : object_title } )
                            setattr( source, 'remote_links', _from )
                            source._p_changed = 1

                            if check_link( remote_links, s_uid ):
                                continue
                            remote_links.append( { 'uid'   : s_uid, \
                                                   'url'   : get_relative_url( source ), \
                                                   'title' : source.Title() } )

                    if remote_links:
                        setattr( obj, 'remote_links', remote_links )
                        check_links.append( [ 'remote_links', archive_url ] )

                    attr_links = {}

                    for attr in category.listAttributeDefinitions():
                        if attr.Type() == 'link':
                            attr_id = attr.getId()
                            attr_value = obj.getCategoryAttribute( attr_id )
                            if not attr_value:
                                continue
                            source = context.portal_catalog.unrestrictedGetObjectByUid( attr_value )
                            if source is None:
                                continue

                            attr_links[ attr_id ] = { 'uid'   : source.getUid(), \
                                                      'url'   : get_relative_url( source ), \
                                                      'title' : source.Title() + source.getInfoForLink() }

                    if attr_links:
                        setattr( obj, 'attr_links', attr_links )
                        check_links.append( ['attr_links', archive_url] )

                    setattr( obj, 'archive_url', archive_url )
                    obj._p_changed = 1
                    r_archived += 1

                if not obj.registry_ids():
                    entry = entry_info = None
                else:
                    entry = getEntry( obj )
                    if entry is not None:
                        registry_id = entry.get('ID')
                        registry_date = entry.get('creation_date')
                        entry_info = {
                            'registry_id'      : registry_id,
                            'object_state'     : object_state,
                            'object_title'     : object_title,
                            'archive_instance' : archive_instance,
                            'archive_url'      : archive_url,
                            'archive_date'     : archive_date,
                            'uid'              : uid
                        }
                        if IsRun:
                            setattr( obj, 'registry_date', registry_date )
                    else:
                        self._log('archive', "= ARC-2[ ERROR ] Bad entry: %s" % object_path)
                        bad_entries.append( archive_url )
                        r_archived = r_archived - 1
                        R_ERRORS += 1
                        continue

                if IsRun and entry is not None:
                    setattr( entry, 'archive_state_information', entry_info )
                    entry._p_changed = 1
                    r_entries += 1

                #if IsRun and self.IsArchiveTrace():
                #    self._log('archive', "... %s" % object_path)

                if IsRun and commit_every > 0 and divmod( r_total_objects, commit_every )[1] == 0:
                    try:
                        transaction.get().commit()
                        r_commited += commit_every
                        r_successful_commit += 1
                        IsError = 0
                    except:
                        R_BAD_COMMIT += 1
                        IsError = 1

                    self._log('archive', "= ARC-2. %s: %s %s %s %s %s %s" % ( 
                        IsError and 'Bad commit' or 'Commit',
                        r_total_objects,
                        r_commited,
                        commit_every,
                        r_invalid,
                        R_ERRORS,
                        r_successful_commit
                        )
                    )

            if apply_threading: interrupt_thread( context, force=1 )

            del objects

        if IsRun:
            if commit_every > 0 and divmod( r_total_objects, commit_every )[1] > 0:
                transaction.get().commit()
                r_successful_commit += 1

        del res
        del folders

        if IsRun:
            self._log('archive', "= ARC-2. FINISHED. Results (total objects, archived, commited, entries, invalid, errors, successful commit, BAD_COMMIT): %s %s %s %s %s %s %s %s" % ( \
                r_total_objects, 
                r_archived,
                r_commited,
                r_entries,
                r_invalid,
                R_ERRORS,
                r_successful_commit,
                R_BAD_COMMIT
                )
            )

            if check_links:
                self._log('archive', "= ARC-2. Check links: %s" % check_links)
        else:
            self._log('archive', "= ARC-2. FINISHED. Checked (total objects, invalid, errors): %s %s %s" % ( \
                r_total_objects, 
                r_invalid,
                R_ERRORS,
                )
            )

        return R_ERRORS

    def _export( self ):
        """
            Export of archive folder
        """
        uname = _getAuthenticatedUser(self).getUserName()
        x = self.getArchiveDescription()

        archive_name = x['name']
        apply_threading = x['apply_threading']
        export_path = x['export_path']
        if not ( export_path and os.path.exists(export_path) ):
            return 1

        instance = self.getPortalObject().getId()
        f = archive_name+'.zexp'
        path = x['path']

        try:
            context = self.unrestrictedTraverse( path )
        except:
            return 1

        self._log('archive', message="Export. Folder %s from %s, run by %s" % ( archive_name, path, uname ))

        try:
            context.manage_exportObject( id=archive_name, download=0, toxml=None )
            self._safety_moving( CLIENT_HOME, export_path, f )
        except Exception, msg_error:
            message = str(msg_error)
            self._log('archive', "Error during export: %s/%s, %s" % ( context.relative_url(), archive_name, message ))
            IsError = 1
        else:
            self._log('archive', "OK (%s)" % f)
            IsError = 0

        if apply_threading: interrupt_thread( context, force=1 )

        return IsError

    def _remove( self ):
        """
            Remove 'arc' catalog
        """
        uname = _getAuthenticatedUser(self).getUserName()
        x = self.getArchiveDescription()

        archive_name = x['name']
        apply_threading = x['apply_threading']
        instance = self.getPortalObject().getId()
        path = x['path']

        try:
            context = self.unrestrictedTraverse( path )
        except:
            return None

        self._log('archive', message="Remove. Folder %s from %s, run by %s" % ( archive_name, path, uname ))

        try:
            context.deleteObjects( [ archive_name ] )
            transaction.get().commit()
        except Exception, msg_error:
            message = str(msg_error)
            self._log('archive', "Error during removing: %s/%s, %s" % ( context.relative_url(), archive_name, message ))
            IsError = 1
        else:
            self._log('archive', "OK")
            IsError = 0

        if apply_threading: interrupt_thread( context, force=1 )

        return IsError

    def _remove_shortcuts( self ):
        """
            Remove invalid archived object's shortcuts
        """
        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            return 1

        x = self.getArchiveDescription()

        apply_threading = x['apply_threading']
        commit_every = x['commit_every']
        threshold = x['threshold']
        instance = self.getPortalObject().getId()
        path = '/%s/storage' % instance

        try:
            context = self.unrestrictedTraverse( path )
        except:
            return None

        self._log('archive', message="Remove shortcuts. Path: %s" % path)

        res = catalog.searchResults( path=path+'%', meta_type='Shortcut', sort_limit=10000 )

        r_total_objects = 0
        r_removed_shortcuts = 0
        r_removed_objects = 0
        r_invalid = 0

        for r in res:
            object_path = r.getPath()
            try: ob = r.getObject()
            except: ob = None

            r_total_objects += 1

            if ob is None: 
                catalog.uncatalog_object( object_path )
                r_removed_shortcuts += 1
                continue

            object_id = r['id']
            source = ob.getObject()

            if source is None:
                try:
                    parent = aq_parent(ob)
                except:
                    r_invalid += 1
                    continue

                parent.manage_delObjects( ids=[ object_id ] ) 
                r_removed_objects += 1

            #if commit_every > 0 and divmod( r_total_objects, commit_every )[1] == 0:
            #    transaction.get().commit()

            if apply_threading: interrupt_thread( context, force=1 )

        del res

        transaction.get().commit()

        self._log('archive', "Removed (total objects, shortcuts, objects, invalid): %s %s %s %s" % ( \
            r_total_objects, 
            r_removed_shortcuts,
            r_removed_objects,
            r_invalid,
            )
        )

        return 0

    def _clean_archive( self, IsRun=None ):
        """
            Remove empty folders inside archive
        """
        uname = _getAuthenticatedUser(self).getUserName()
        x = self.getArchiveDescription()

        archive_name = x['name']
        apply_threading = x['apply_threading']
        instance = self.getPortalObject().getId()
        path = '%s/%s' % ( x['path'], archive_name )

        try:
            context = self.unrestrictedTraverse( path )
        except:
            return None

        self._log('archive', message="Clean archive. Path: %s, run by %s" % ( path, uname ))

        keep_object_ids = []
        remove_masks = [ re.compile(x) for x in ( r'[&=#$A-Za-z0-9._\-+%]*', ) ]

        removed_objects, r_removed, R_ERRORS = cleaner( context, path, keep_object_ids, remove_masks, IsRun, apply_threading )

        if IsRun and self.IsArchiveTrace() and removed_objects:
            for p in removed_objects:
                self._log('archive', "... %s" % p)

        if IsRun: transaction.get().commit()

        if IsRun:
            self._log('archive', "Removed %s folders, errors: %s" % ( \
                len(removed_objects),
                R_ERRORS,
                )
            )
        else:
            self._log('archive', "Should be removed %s folders" % ( \
                len(removed_objects),
                )
            )

        return R_ERRORS

    def _clean_storage( self, IsRun=None ):
        """
            Remove empty folders inside storage
        """
        uname = _getAuthenticatedUser(self).getUserName()
        x = self.getArchiveDescription()

        archive_name = x['name']
        apply_threading = x['apply_threading']
        portal = self.getPortalObject()
        instance = self.getPortalObject().getId()

        keep_object_ids = ['import']
        remove_masks = [ re.compile(x) for x in ( '20(\d)*', ) ]
        removed_objects = []
        r_removed = 0
        R_ERRORS = 0

        segments = [ x.physical_path() for x, extended in DefaultSegment( portal, extended=1 ) if x is not None ]

        for path in segments:
            try: 
                context = self.unrestrictedTraverse( path )
            except:
                continue
            self._log('archive', message="Clean storage. Path: %s, run by %s" % ( path, uname ))

            x = cleaner( context, path, keep_object_ids, remove_masks, IsRun, apply_threading )

            removed_objects += x[0]
            r_removed += x[1]
            R_ERRORS += x[2]

            if IsRun and self.IsArchiveTrace() and x[0]:
                for p in x[0]:
                    self._log('archive', "... %s" % p)

            if IsRun: transaction.get().commit()

            if IsRun:
                self._log('archive', "Removed %s folders, errors: %s" % ( \
                    len(x[0]),
                    x[2],
                    )
                )
            else:
                self._log('archive', "Should be removed %s folders" % ( \
                    len(x[0]),
                    )
                )

        return R_ERRORS

    def ImportToArchive( self ):
        """
            Import zexp-packages to archive
        """
        if self.IsArchiveImportRunning():
            return None
        if not self.IsArchiveImportScheduleTaskActivated():
            return None
        catalog = getToolByName( self, 'portal_catalog', None )
        followup = getToolByName( self, 'portal_followup', None )
        scheduler = getToolByName( self, 'portal_scheduler', None )
        if None in ( catalog, followup, scheduler ):
            return None
        task = scheduler.getScheduleElement( self._import_schedule_id )
        if task is None:
            return None

        x = self.getArchiveSchedule()

        import_path = x['import_path']
        if not ( import_path and os.path.exists(import_path) ):
            return None
        path = x['path']
        try:
            context = self.unrestrictedTraverse( path )
        except:
            return None
        ids = [ f for f in os.listdir(import_path) if f.endswith('.zexp') ]
        if not ids:
            return None
        apply_threading = x['apply_threading']
        lock_catalog = x['lock_catalog']

        import_archive_log = getattr( self, '_import_archive_log', [] )

        setattr( self, '_import_running', 1 )
        task.suspend()

        if lock_catalog:
            followup.lockCatalog()

        self._make_DB_copy()

        for id in ids:
            message = []
            IsError = 0
            self._log('archive', message="Import. Package %s from %s into %s" % ( id, import_path, path ))

            import_from = import_path
            import_to = os.path.join(INSTANCE_HOME, 'import')

            try:
                self._safety_moving( import_from, import_to, id, no_safe=1 )
            except Exception, msg_error:
                message.append( str(msg_error) )
                self._log('archive', "Error during moving %s from %s to %s: %s" % ( id, import_from, import_to, message[-1] ))
                IsError = 1

            if lock_catalog: catalog.lockCatalog()

            try:
                context.manage_importObject( file=id, REQUEST=None, set_owner=0 )
            except Exception, msg_error:
                message.append( str(msg_error) )
                self._log('archive', "Error during import %s: %s, context: %s" % ( id, message[-1], context.relative_url() ))
                IsError = 1

            if lock_catalog: catalog.unlockCatalog()

            import_from = import_to
            import_to = os.path.join(import_path, 'archive')

            try:
                self._safety_moving( import_from, import_to, id, no_safe=1 )
            except Exception, msg_error:
                message.append( str(msg_error) )
                self._log('archive', "Error during moving %s from %s to %s: %s" % ( id, import_from, import_to, message[-1] ))
                IsError = 1

            counter = None

            try:
                oid = id.replace('.zexp', '')
                ob = context._getOb( id=oid )
            except Exception, msg_error:
                message.append( str(msg_error) )
                self._log('archive', "Container does not exist: id %s, %s" % ( oid, message[-1] ))
                IsError = 1
            else:
                if lock_catalog:
                    catalog.reindexObject( ob )
                    catalog.setup( force=1, root_object=ob )
                counter = catalog.countResults( REQUEST=None, path='%s%%' % ob.physical_path(), implements='isHTMLDocument' )

            if not IsError:
                message.append( 'Package was imported successfully' )

            import_archive_log.append( ( DateTime(), import_path, id, path, message, IsError, counter ) )
            self._import_archive_log = import_archive_log
            self._p_changed = 1

            transaction.get().commit()

            if not IsError:
                self._log('archive', "OK")

            if apply_threading: interrupt_thread( context, force=1 )

        if lock_catalog:
            followup.unlockCatalog()
            followup.setup( 1 )

        setattr( self, '_import_running', 0 )
        task.resume()

        self._log('archive', ".")

        return IsError

    def getImportArchiveLog( self ):
        """
            Returns Import Archive log
        """
        res = []
        import_archive_log = getattr( self, '_import_archive_log', [] )

        if not import_archive_log:
            return res

        import_archive_log.sort()
        import_archive_log.reverse()

        res = [ { 'date'        : x[0], \
                  'import_path' : x[1], \
                  'id'          : x[2], \
                  'path'        : x[3], \
                  'message'     : x[4], \
                  'IsError'     : x[5], \
                  'counter'     : x[6], \
                } for x in import_archive_log ]

        return res

    def locate( self, uid, mode=None, REQUEST=None ):
        """
            We try to find an object with given uid somewhere
        """
        IsError = 0

        if not mode:
            IsError, res = self.sync_property( 'locate', None, None, 1, uid, 1 )
        else:
            catalog = getToolByName( self, 'portal_catalog', None )
            if catalog is None:
                return (0, '')
            res = catalog.unrestrictedSearch( check_permission=0, nd_uid=uid )
            try:
                ob = res[0].getObject() #_unrestrictedGetObject()
            except:
                IsError = 1
                ob = None
            if ob is None:
                return ( IsError, '' )
            url = ob.absolute_url( canonical=1 )
            return ( IsError, url )

        if REQUEST is not None:
            for url in filter(None, res):
                return REQUEST.RESPONSE.redirect( url )

        return ( IsError, res )

InitializeClass( ServicesTool )


def IsFolderExist( context, id, title, path, IsRun=None ):
    if context is None: return ( None, 0 )
    IsCreated = 0
    IsBreak = 0
    for i in range(0,2):
        try: folder = context.unrestrictedTraverse( path )
        except: folder = None
        if folder is not None:
            if folder.relative_url()[0 : len(path)] != path:
                folder = None
        if folder is None:
            if not IsBreak and IsRun:
                context.manage_addHeading( id=id, title=' '+title, set_owner=0 )
                IsCreated = 1
                IsBreak = 1
            else:
                return ( None, 0 )
    return ( folder, IsCreated )

def check_role( context, role ):
    return context.users_with_local_role( role ) or []

def get_relative_url( obj, instance=None ):
    url = obj.physical_path() # relative_url()
    if instance:
        url = url.replace( '/'+instance, '' )
    return url

def sort_objects( values ):
    if not values: return []
    res = []
    for obj in values:
        if not ( obj.implements('isDocument') and obj.implements('isCategorial') ):
            continue
        object_date = DateTime( obj.CreationDate() )
        res.append( (object_date, obj) )
    res.sort()
    return [ x[1] for x in res ]

def cleaner( context, path, keep_object_ids, remove_masks, IsRun=None, apply_threading=None ):
    removed_objects = []
    r_removed = 0
    R_ERRORS = 0

    try:
        folder = context.unrestrictedTraverse( path )
    except Exception, msg_error:
        logger.error('%s, path: %s' % ( str(msg_error), path ))
        return ( [], 0, 1, )
        
    IsBreak = 0
    ids = []

    query = {}
    query['implements'] = 'isContentStorage'

    res = context.portal_catalog.searchResults( parent_path=path, sort_on='id', **query )

    for x in res:
        if remove_masks:
            IsApply = 0
            for mask in remove_masks:
                if mask.search(x['id']) is not None:
                    IsApply = 1
                    break

        obj = x.getObject()
        if obj is None:
            continue

        object_id = obj.getId()
        object_path = obj.relative_url()

        if keep_object_ids and object_id in keep_object_ids:
            continue

        if len(obj.objectValues()) > 0:
            r = cleaner( context, object_path, keep_object_ids, remove_masks, IsRun, apply_threading )
            for p in r[0]:
                if p in removed_objects: continue
                removed_objects.append(p)
            R_ERRORS += r[2]
        if IsApply:
            if not obj.objectIds():
                removed_objects.append( object_path )
                ids.append( object_id )

    if ids:
        if IsRun:
            try:
                folder.deleteObjects( ids )
                r_removed += len(ids)
            except:
                logger.error('Cannot remove folders, path: %s, ids: %s' % ( path, ids ))
                R_ERRORS += 1
        else:
            r_removed += len(ids)

    del folder

    if apply_threading: interrupt_thread( context, force=1 )

    return ( removed_objects, r_removed, R_ERRORS, )