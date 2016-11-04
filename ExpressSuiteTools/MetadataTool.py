"""
MetadataTool, DocumentCategory, CategoryAttribute classes
$Id: MetadataTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 07/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from types import DictType, ListType, TupleType, StringType
from string import lower

from Acquisition import Implicit, aq_base
from AccessControl import ClassSecurityInfo
from OFS.SimpleItem import Item
from DateTime import DateTime

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.ActionInformation import ActionInformation
from Products.CMFCore.Expression import Expression
from Products.CMFCore.utils import getToolByName, _getAuthenticatedUser

from Products.CMFDefault.MetadataTool import MetadataTool as _MetadataTool, DEFAULT_ELEMENT_SPECS
from Products.CMFDefault.Document import Document

import Config
from DocflowLogic import DocflowLogic
from DefaultCategories import setupWorkflowVars
from DepartmentDictionary import departmentDictionary
from TaskBrains import listTaskBrains
from TaskDefinitionFactory import TaskDefinitionFactory
from TaskDefinitionNotification import TaskDefinitionNotification
from TaskTemplateContainer import TaskTemplateContainer
from TaskTemplateContainerAdapter import TaskTemplateContainerAdapter
from Resultcodes2Transition import Resultcodes2Transition
from Resultcodes2Transition import Resultcodes2TransitionModel
from SimpleObjects import Persistent, ToolBase, ContainerBase, InstanceBase
from VersionWorkflow import VersionWorkflowLogic

from Utils import InitializeClass, getObjectByUid, joinpath, uniqueValues, isInstance

from CustomDefinitions import CheckCustomOption

MAX_SIZE_OF_ID = 3
DELIMETER = '$'


class MetadataTool( ToolBase, ContainerBase, _MetadataTool ):
    """
        Portal metadata tool
    """
    _class_version = 1.0

    id = 'portal_metadata'
    meta_type = 'ExpressSuite Metadata Tool'

    meta_types = ( \
                   {'name':'Category',
                    'permission':CMFCorePermissions.ManagePortal,
                    'action':''},
                  )

    manage_options = _MetadataTool.manage_options + \
                     ContainerBase.manage_options[:-1] # exclude 'Properties'
                     # + ToolBase.manage_options

    security = ClassSecurityInfo()

    _actions = ( \
         ActionInformation( \
                   id='manageSubjects'
                 , title='Document types'
                 , description='Manage valid document types'
                 , action=Expression( text='string: ${portal_url}/metadata_subjects_form' )
                 , permissions=(CMFCorePermissions.ManagePortal,)
                 , category='global'
                 , condition=None
                 , visible=0
                 ),
         ActionInformation( \
                   id='manageCategories'
                 , title='Document categories'
                 , action=Expression( text='string: ${portal_url}/manage_categories_form' )
                 , permissions=(CMFCorePermissions.ManagePortal,)
                 , category='global'
                 , condition=None
                 , visible=1
                 ),
        ) + ToolBase._actions

    def __init__( self, publisher=None, element_specs=DEFAULT_ELEMENT_SPECS ):
        """
            Initialize class instance
        """
        ToolBase.__init__( self )
        _MetadataTool.__init__( self, publisher, element_specs )

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not ToolBase._initstate( self, mode ):
            return 0

        if hasattr( self, 'categories' ):
            for category in self.categories.values():
                self._setObject( category.getId(), category, set_owner=0 )
            delattr(self, 'categories')

        for category_id in self.objectIds():
            self._upgrade( category_id, CategoryDefinition )

        if getattr( self, 'resultcodes2Transition', None ) is None:
            self.resultcodes2Transition = Resultcodes2Transition()

        if getattr( self, 'docflowLogic', None ) is None:
            if getattr( self, 'docflowLogic1', None ):
                del self.docflowLogic1
            self.docflowLogic = DocflowLogic()

        if getattr( self, 'taskTemplateContainerAdapter', None ) is None:
            self.taskTemplateContainerAdapter = TaskTemplateContainerAdapter()

        if getattr( self, 'taskDefinitionFactory', None ) is None:
            self.taskDefinitionFactory = TaskDefinitionFactory()
            self.taskTemplateContainerAdapter.setTaskDefinitionFactory( self.taskDefinitionFactory )

        if getattr( self, 'versionWorkflowLogic', None ) is None:
            self.versionWorkflowLogic = VersionWorkflowLogic()

        return 1

    def _workflow_id( self, id ):
        return 'category_%s' % id

    def addCategory( self, cat_id, title='', default_workflow=1, wf_id=None, allowed_types=[], lock_timeout=None ):
        """
            Adds a new document category - creates new instance of DocumentCategory class and adds it to the self.categories hash

            Arguments:

                'cat_id' -- New category id string.

                'title' -- Category title.

                'default_workflow' -- Determines whether the category should be bound to the default workflow.

                'wf_id' -- Category workflow id. The workflow with a given id will be associated with the category.

                'allowed_types' -- List of allowed objects types that are allowed to be in the category.

                'lock_timeout' -- timeout for locking category documents

            Result:

                Reference to the created category object.
        """
        cat_id = str(cat_id).strip()
        self._checkId(cat_id)

        workflow = getToolByName( self, 'portal_workflow', None )
        if workflow is None:
            return

        category = CategoryDefinition( cat_id, title )
        self._setObject( cat_id, category, set_owner=0 )

        if wf_id is None:
            wf_id = self._workflow_id( cat_id )
            workflow.createWorkflow( wf_id )
            workflow.bindWorkflow( wf_id )
            if default_workflow:
                wf = workflow[wf_id]
                setupWorkflowVars( wf )

        category.setWorkflow( wf_id )

        if allowed_types:
            category.setAllowedTypes( allowed_types )

        if lock_timeout:
            category.setLockTimeout( lock_timeout )

        return category.__of__(self)

    def renameCategory( self, id, new_id ):
        """
            This changes category/workflow object's id
        """
        workflow = getToolByName( self, 'portal_workflow', None )
        if workflow is None:
            return
        category = self.getCategoryById( id )
        if category is None:
            return
        wf_id = self._workflow_id( id )
        wf = category.getWorkflow() or workflow[ wf_id ]
        if wf is None:
            return

        new_wf_id = self._workflow_id( new_id )

        wf._setId( new_wf_id )
        workflow._delObject( wf_id )
        workflow._setObject( new_wf_id, wf )
        workflow.bindWorkflow( new_wf_id )

        category._setId( new_id )
        self._delObject( id )
        self._setObject( new_id, category, set_owner=0 )
        category.setWorkflow( new_wf_id )

    def deleteCategories( self, ids ):
        """
            Deletes selected categories from "categories" hash.

            Arguments:

                'ids' -- list of categories ids to be deleted

            Notes:

                Category will not be deleted if at least one object with this
                category exists in the portal.
        """
        catalog = getToolByName(self, 'portal_catalog', None)
        workflow = getToolByName(self, 'portal_workflow', None)
        
        message = ''
        
        if not ids:
            return
        
        for id in ids:
            if not id:
                continue
            
            category = self.getCategoryById(id)
            docs = catalog.searchResults( category = category.getId(), implements='isCategorial' )
            dependents = category.listDependentCategories()
            
            if category and not docs and not dependents:
                workflow.manage_delObjects([category.Workflow(),])
                self._delObject(id)
                message = 'Categories were removed'
            elif docs:
                message = 'Category was not removed, documents are existed. You can try reindex catalog'
                break
            elif dependents:
                message = 'Category was not removed, dependents are existed'
                break
        
        return message

    def getCategoryById( self, id ):
        """
            Returns category by given id.

            Arguments:

                'id' -- Category id string.

            Result:

                Category object (an instance of the DocumentCategory class)
        """
        if not id:
            return None
        return self._getOb( id, None )

    def getCategoryTitle( self, id ):
        """
            Returns category title by given id
        """
        category = self.getCategoryById(id)
        if not category:
            return None
        return category.Title()

    def getCategoryStatesList( self, id ):
        """
            Returns category states list by given id
        """
        wf_id = self._getWorkflowByCategory(id)
        if not wf_id:
            return None
        workflow = getToolByName( self, 'portal_workflow', None )
        if workflow is None:
            return None

        res = []
        for state in workflow.getSortedStateList(wf_id):
            title = workflow.getStateTitle(wf_id, state)
            res.append( { 'id' : state, 'title' : title or state } )

        return tuple(res)

    def getStateTitle( self, id, state ):
        """
            Returns state title by given category id
        """
        wf_id = self._getWorkflowByCategory(id)
        if not wf_id:
            return None
        workflow = getToolByName(self, 'portal_workflow', None)
        if workflow is None:
            return None
        return workflow.getStateTitle(wf_id, state)

    security.declarePublic( 'listSupervisorModes' )
    def listSupervisorModes( self ):
        """ Returns list of supervisor managed modes
        """
        return ( { 'id' : 'default', 'title' : 'Supervisor by default', 'description' : 'In this mode supervisor should vise the task before finalize', 'default' : 1 }, \
                 { 'id' : 'request', 'title' : 'Send to supervisor after commission was realized', 'description' : 'In this mode supervisor will manage the task after commission was checked by author', 'default' : 0 }, \
                 { 'id' : 'info',    'title' : 'Inform supervisor about commission', 'description' : 'In this mode supervisor will be informed about commission', 'default' : 0 }, \
                 )

    security.declarePublic( 'listConfirmationTypes' )
    def listConfirmationTypes( self ):
        """ Returns list of confirmation request types
        """
        return ( { 'key' : 'simultaneously',  'name' : 'simultaneously request' }, \
                 { 'key' : 'confirm_by_turn', 'name' : 'confirm by turn' }, \
                 { 'key' : 'cycle_by_turn',   'name' : 'cycle by turn' }, \
                 )

    security.declarePublic( 'listRoutingSubfoldesTypes' )
    def listRoutingSubfoldesTypes( self ):
        """ Returns list of routing subfoldes types which will be created automatically by workflow
        """
        return ( { 'key' : 'by_month',  'name' : 'by monthes' }, \
                 { 'key' : 'by_day',    'name' : 'by days' }, \
                 )

    security.declarePublic( 'listBrainsTypes' )
    def listBrainsTypes( self, visible=None, sort=None ):
        """ Returns list of registered task brains types
        """
        brains_types = []
        for x in listTaskBrains():
            tti = getattr( x, 'task_type_information', None )
            if tti and ( visible is None or tti['visible'] == visible ):
                brains_types.append( { 'id'      : tti['id'], \
                                       'title'   : tti['title'], \
                                       'sortkey' : tti['sortkey'], \
                                       } )
        if brains_types and sort:
            brains_types.sort( lambda x, y: cmp(x['sortkey'], y['sortkey']) )
        return brains_types

    security.declarePublic( 'listCategories' )
    def listCategories( self, ob=None, sort=None ):
        """
            Returns the list of allowed document categories.

            Arguments:

               'ob' -- If not None and 'ob' is only the categories allowed in the
                       'ob' object will be listed. In case the 'ob' is of string
                       type, it is used as the object meta type.

            Result:

                List of category definition object references.
        """
        categories = self.objectValues()
        if type(ob) is StringType:
            meta_type = ob
        else:
            meta_type = ob and ob.meta_type

        if meta_type:
            categories = filter( lambda c, t=meta_type: c.isTypeAllowed(t), categories )

        if sort:
            categories.sort( lambda x, y: cmp(x.Title(), y.Title()) )

        return categories

    # XXX: must be removed soon
    security.declarePublic( 'getCategories' )
    def getCategories( self, type_id=None, custom=None ):
        """
            Returns the list of categories allowed for given content type.

            If content type is not specified, returns list of all available categories.

            Arguments:

                'type_id' -- content type to list categories for

            Note:

                This method is obsolete, listCategories method should be used instead.

            Result:

                List of category definition object references.

        """
        cats = self.objectValues()
        if type_id is not None:
            cats = filter( lambda c, t=type_id: c.isTypeAllowed(t), cats )

        if custom and type(custom) is StringType:
            cats = filter( lambda c, key=custom, n=len(custom): c.getId()[:n] == key, cats )

        # Sorting by MessageCatalog
        msg = getToolByName( self, 'msg' )
        cats.sort(lambda x, y, msg=msg: cmp(lower(msg(x.Title())), lower(msg(y.Title()))) )

        return cats

    security.declarePublic( 'getCategoryIds' )
    def getCategoryIds( self, type_id=None ):
        """
          Returns the list of categories ids for given content type.
          if content type is not specified, returns list of all available categories ids

          Arguments:

            'type_id' -- content type to list category ids for

          Note:

            This method is obsolete, listCategories should be used instead.

          Result:

            list of strings - categories ids

        """
        return self.objectIds()

    def getTemplatesFolderPath( self ):
        """
          Returns path to document templates folder.
          This path is used for searching in templates folder

          Result:

            Path from Zope root to document templates folder

        """
        p_url = self.portal_url.getPortalObject().getPhysicalPath()
        path = joinpath(p_url, 'storage', 'system', 'templates')
        return path

    security.declareProtected( CMFCorePermissions.ManagePortal, 'actionOverTable' )
    def actionOverTable( self, REQUEST ):
        """ make action on table """
        c_id = REQUEST.get('c_id', '')
        if c_id=='':
            return 'c_id not specified'
        self.resultcodes2Transition.setModel( self.getCategoryById(c_id).resultcodes2TransitionModel )

        urlString = ''
        ret = self.resultcodes2Transition.controller.makeActionByRequest( REQUEST )
        if ret != '': urlString = '?ret='+ret
        REQUEST.RESPONSE.redirect( 'task_template_summary' + urlString + '#resultcode2transition')

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setTransitionTaskTemplate' )
    def setTransitionTaskTemplate( self, c_id, transition, task_templates ):
        """ 
            Are called from skins/categories/workflows.py
            task_templates = [ 'template_id1', ... ]
        """
        self.getCategoryById(c_id).transition2TaskTemplate[transition] = task_templates
        self.getCategoryById(c_id)._p_changed = 1

    security.declareProtected( CMFCorePermissions.View, 'listTransitionsIdsWithNotification' )
    def listTransitionsIdsWithNotification( self, category_id ):
        """
            Returns list of transitions ids in which object(s) of TaskDefinitionNotification is placed (passed).

            Arguments:

                'category_id' -- id of the category
        """
        return {}

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setState2TaskTemplateToDie' )
    def setState2TaskTemplateToDie( self, c_id, state, task_templates ):
        """
            Called from skins/categories/workflows.py
            task_templates = { 'template_id1': 'result_code1', ... }
        """
        self.getCategoryById(c_id).state2TaskTemplateToDie[state] = task_templates
        self.getCategoryById(c_id)._p_changed = 1

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getGuardPermissions' )
    def getGuardPermissions( self, guard ):
        return guard.permissions

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getGuardAllowedUsers' )
    def getGuardAllowedUsers( self, guard, mode=None ):
        try:
            if not guard.expr: return None
        except:
            return None

        expr = str(guard.expr.text)
        n = expr.find('in [')
        if not n:
            return None
        x = expr[n+3:]
        try:
            ids = eval( x )
        except:
            return None

        results = []
        membership = getToolByName( self, 'portal_membership' )
        for id in ids:
            member = membership.getMemberById( id )
            if member:
                member_name = mode and member.getMemberBriefName( mode ) or member.getMemberName()
                results.append( {'user_id': id, 'user_name': member_name } )

        results.sort(lambda x, y: cmp(lower(x['user_name']), lower(y['user_name'])))
        return results

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getManagedPermissions_' )
    def getManagedPermissions_( self ):
        return Config.ManagedPermissions

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getManagedRoles_' )
    def getManagedRoles_( self ):
        return Config.ManagedRoles

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getXML' )
    def getXML( self, REQUEST ):
        """ xml """
        str = ''
        str += '<?xml version="1.0" encoding="windows-1251"?>\n'
        #str += '<?xml-stylesheet type="text/xsl" media="text/html" href="%s/default2view.xsl"?>\n' % self.absolute_url()
        str += '<!-- generated %s -->\n' % DateTime()
        str += '<category-list>'
        portal_workflow = getToolByName( self, 'portal_workflow' )

        c_id = REQUEST.get( 'c_id' )

        if c_id:
            c_ids = (c_id,)
        else:
            c_ids = self.getCategoryIds()
        for c_id in c_ids:
            cat_def = self.getCategoryById(c_id)
            str += '\n'
            str += '<category id="%s" title="%s">\n' % ( cat_def.id, cat_def.title )

            str += '  <base-categories>\n'
            for base in cat_def.listBases():
                str += '    <category id="%s"/>\n' % base.id
            str += '  </base-categories>\n\n'

            str += '  <allowed-types>\n'
            for at in cat_def.listAllowedTypes():
                str += '    <type id="%s"/>\n' % at
            str += '  </allowed-types>\n\n'

            str += '  <metadata>\n'
            for attr in cat_def.listAttributeDefinitions():
               if attr.isInCategory( self.getCategoryById( c_id ) ):
                   id = attr.getId()
                   type_attr = attr.Type()
                   title =  attr.Title()
                   default = attr.getDefaultValue()
                   str += '    <field id="%s" type="%s" title="%s" default="%s"/>\n' % ( id, type_attr, title, default )
            str += '  </metadata>\n\n'

            wf_def = portal_workflow[cat_def.Workflow()]
            workflow_str = '  <workflow>\n'

            workflow_str += '    <state-list>\n'
            workflow_str += '      <initial-state id="%s"/>\n' % wf_def.initial_state
            for state in wf_def.states.values():
                if not wf_def.states.isPrivateItem(state):
                    continue
                title = state.title.replace( '"', '&quot;' )
                state_str = '      <state id="%s" title="%s">\n' % ( state.id, title )
                state_str += '        <transitions>\n'
                for transition_id in state.transitions:
                    state_str += '          <transition id="%s"/>\n' % transition_id
                state_str += '        </transitions>\n'
                state_str += '        <permissions>\n'
                for perm_id in state.permission_roles.keys():
                    roles = state.permission_roles[perm_id]
                    if type(roles) is type([]):
                        acquire = '1'
                    else:
                        acquire = '0'
                    perm_str = '          <permission id="%s" acquire="%s">\n' % ( perm_id, acquire )
                    for role in roles:
                        perm_str += '            <role id="%s"/>\n' % role
                    perm_str += '          </permission>\n'
                    state_str += perm_str
                state_str += '        </permissions>\n'
                state_str += '      </state>\n'
                workflow_str += state_str
            workflow_str += '    </state-list>\n'

            workflow_str += '    <transition-list>\n'
            for tr_def in wf_def.transitions.values():
                if not wf_def.transitions.isPrivateItem(tr_def):
                    continue
                title = tr_def.title.replace( '"', '&quot;' )
                actbox_name = tr_def.actbox_name.replace( '"', '&quot;' )
                transition_str = '      <transition id="%s" title="%s" actbox-name="%s" new-state="%s">\n' % ( tr_def.id, title, actbox_name, tr_def.new_state_id )
                tr_guard = tr_def.guard

                transition_str += '        <guard-roles>\n'
                for role in tr_guard.roles:
                    transition_str += '          <role id="%s"/>\n' % role
                transition_str += '        </guard-roles>\n'

                transition_str += '        <guard-permissions>\n'
                for permission in tr_guard.permissions:
                    transition_str += '          <permission id="%s"/>\n' % permission
                transition_str += '        </guard-permissions>\n'

                if tr_def.trigger_type == 2:
                    transition_str += '        <workflow-method/>\n'
                transition_str += '      </transition>\n'
                workflow_str += transition_str
            workflow_str += '    </transition-list>\n'

            workflow_str += '  </workflow>\n'
            str += workflow_str
            str += '</category>\n\n'
        str += '</category-list>\n'
        REQUEST.RESPONSE.setHeader( 'content-type', 'text/xml'  )
        return str

    security.declareProtected( CMFCorePermissions.View, 'listLanguageCategoryIds' )
    def listLanguageCategoryIds( self, categories=None ):
        res = []
        if not categories:
            categories = self.listCategories()
        for category in categories:
            if category.getImplementLanguage():
                res.append( category.getId() )
        return res

    def _getWorkflowByCategory( self, id ):
        category = self.getCategoryById(id)
        if category is None:
            return None
        wf_id = category.Workflow()
        if not wf_id:
            return None
        return wf_id

InitializeClass( MetadataTool )


class CategoryDefinition( InstanceBase, Item ):
    """ Document category class """
    _class_version = 1.0

    meta_type = 'Category'

    security = ClassSecurityInfo()

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setTitle' )

    allowed_types = ()
    edit_template_fields_only = ''

    def __init__( self, id, title='' ):
        """ Instance constructor
        """
        InstanceBase.__init__( self, id )
        self.title = title
        self.template = []
        self.default_template = None
        self.forbid_free_cookedbody = ''
        self.reply_to_action = None
        self.lock_attachments = None
        self.implement_language = None

        self._initId()
    
    def __cmp__( self, other ):
        # compare category objects by identifier
        if other is None:
            return 1
        elif isInstance( other, CategoryDefinition ):
            other = other.getId()
        elif type(other) is not StringType:
            raise TypeError, other
        return cmp( self.getId(), other )

    def view( self, REQUEST=None ):
        """
          The default view of the entry contents
        """
        REQUEST = REQUEST or self.REQUEST
        return self.index_html( REQUEST, REQUEST.RESPONSE )

    def index_html( self, REQUEST, RESPONSE ):
        """
           Returns the entry contents
        """
        return self.main_category_form( self, REQUEST )

    def _initId( self ):
        self.resultcodes2TransitionModel.setCategoryId( self.id )

    def _initstate( self, mode ):
        """
           Initialize attributes
        """
        if not InstanceBase._initstate( self, mode ):
            return 0

        if getattr(self, 'attributes', None) is None:
            self.attributes = ContainerBase()
            if getattr(self, 'fields', None):
                for id, value in self.fields.items():
                     self.attributes._setObject( id, value )
                     self.attributes._upgrade(id, CategoryAttribute)
                del self.fields

        if getattr( self, 'template', None ) is None:
            self.template = []

        if getattr( self, '_bases', None ) is None:
            self._bases = ()

        if not hasattr(self, '_lock_timeout') or self._lock_timeout is None:
            self._lock_timeout = 1800

        if getattr( self, 'taskTemplateContainer', None  ) is None:
            self.taskTemplateContainer = TaskTemplateContainer()

        if getattr( self, 'resultcodes2TransitionModel', None  ) is None:
            self.resultcodes2TransitionModel = Resultcodes2TransitionModel()
            self.resultcodes2TransitionModel.setTaskTemplateContainer( self.taskTemplateContainer )
            if self.id:
                # in case if _initstate are called for
                # existing instance, we have to initialize instance by category_id
                # (otherwise, when instance are created,
                # self.id='' and initialization happened in __init__)
                self._initId()
        if getattr( self, 'transition2TaskTemplate', None ) is None:
            # transition2TaskTemplate =
            #   { 'transition_id1':
            #     [ 'task_template_id1', 'task_template_id2', ... ],
            #     ...
            #   }
            self.transition2TaskTemplate = {}
        if getattr( self, 'state2TaskTemplateToDie', None ) is None:
            # state2TaskTemplateToDie =
            #   { 'state_id1':
            #     { 'task_template_id1': 'result_code1' , ... },
            #     ...
            #   }
            self.state2TaskTemplateToDie = {}
        if not hasattr( self, 'allow_only_single_version' ):
            # allow_only_single_version =
            #   { 'state_id1': 'transition_for_exclude1', 'state_id2', 'transition_for_exclude2', ... }
            self.allow_only_single_version = {}

        if getattr( self, 'default_template', None  ) is None:
            self.default_template = ''

        if getattr( self, 'forbid_free_cookedbody', None  ) is None:
            self.forbid_free_cookedbody = ''

        if getattr( self, 'reply_to_action', None  ) is None:
            self.reply_to_action = None

        if getattr( self, 'lock_attachments', None  ) is None:
            self.lock_attachments = None

        if getattr( self, 'implement_language', None  ) is None:
            self.implement_language = None

        valid_bases = []
        bases_changed = 0

        for base in self._bases:
            if type( base ) is not StringType:
                base = base.getId()
                bases_changed = 1
            valid_bases.append( base )

        if bases_changed:
            self._bases = tuple( valid_bases )

        return 1

    def __cmp__( self, other ):
        # compare category objects by identifier
        if other is None:
            return 1
        elif isInstance( other, CategoryDefinition ):
            other = other.getId()
        elif type(other) is not StringType:
            raise TypeError, other
        return cmp( self.getId(), other )

    def view( self, REQUEST=None ):
        """
          The default view of the entry contents
        """
        REQUEST = REQUEST or self.REQUEST
        return self.index_html( REQUEST, REQUEST.RESPONSE )

    def index_html( self, REQUEST, RESPONSE ):
        """
           Returns the entry contents
        """
        return self.main_category_form( self, REQUEST )

    security.declarePublic( 'Workflow' )
    def Workflow( self ):
        """
            Returns the associated workflow id.

            Note:

                This method is obsolete, getWorkflow should be used instead.

            Result:

                String.
        """
        return self.workflow

    def getWorkflow( self ):
        """
            Returns the associated workflow object.

            Result:

                Workflow definition object.
        """
        workflow = getattr( self, 'workflow', None )
        if type(workflow) is StringType:
            wftool = getToolByName( self, 'portal_workflow', None )
            if wftool is None:
                return None
            workflow = wftool.getWorkflowById( workflow )
        return workflow

    security.declarePrivate( 'setWorkflow' )
    def setWorkflow( self, workflow ):
        """
            Sets the category workflow.

            Arguments:

                'workflow' -- workflow to bind
          """
        self.workflow = workflow

    security.declarePublic( 'Template' )
    def Template( self ):
        """
            Returns the associated document template properties list.

            Result:

                Document properties, dictionary.
        """
        return self.template

    security.declarePublic( 'getDefaultTemplate' )
    def getDefaultTemplate( self ):
        """
            Returns the associated default document template uid.

            Result:

                Document uid, string
        """
        default_template = getattr(self, 'default_template', None)

        if default_template is None:
            if hasattr(self, 'template') and self.template and type(self.template) is ListType:
                self.default_template = self.template[ 0 ]['uid']
            else:
                self.default_template = None
            self._p_changed = 1

        return default_template

    security.declarePublic( 'setDefaultTemplate' )
    def setDefaultTemplate( self, uid=None ):
        """
            Sets the associated default document template uid.
        """
        if uid:
            self.default_template = uid

    security.declarePublic( 'listTemplates' )
    def listTemplates( self ):
        """
            Returns list of template uid, template title, template document URL and template properties
            Exm:
                [(<template_uid:string>, <template_title:string>, <template_url:string>, <mode_1:{1|0}> ... <mode_N:{1|0}> ),
                    ...
                ]
            if can't give template document by template uid, template_title =None and template_url = None
        """
        returned = []

        if hasattr(self, 'template') and self.template:
            for item in self.template:
                try:
                    if not item or not item.keys():
                        break
                except:
                    returned = self.template = []
                    break

                uid = item['uid']

                try: template_edit_fields_only = item['template_edit_fields_only'] 
                except: template_edit_fields_only = None
                try: template_use_translate = item['template_use_translate']
                except: template_use_translate = None
                try: template_use_facsimile = item['template_use_facsimile']
                except: template_use_facsimile = None
                try: wysiwyg_restricted = item['wysiwyg_restricted']
                except: wysiwyg_restricted = None

                template_obj = getObjectByUid(self, uid)

                if template_obj is not None:
                    returned.append( ( uid, template_obj.Title(), template_obj.absolute_url(), 
                                template_edit_fields_only, 
                                template_use_translate,
                                template_use_facsimile,
                                wysiwyg_restricted
                            ) )
                else:
                    # TODO: Template document not found. What should we do?
                    returned.append( (uid, None, None, 0, 0, 0, 0) )

        return returned

    security.declareProtected( CMFCorePermissions.ManagePortal, 'addTemplate' )
    def addTemplate( self, template ):
        """
            Add the category template. "template" property stores document uid

            Arguments:

                'template' -- Uid of the document to be associated with category, "template" is a string 'uid:'+uid

            Notes:

                If "template" property is None or an empty list, "forbid_free_cookedbody" automatically resets to false.
        """
        uid = template[4:] #template is a string 'uid:'+uid
        if not uid: return 0

        new_template = { 'uid' : uid, 
                         'template_edit_fields_only' : 0, 
                         'template_use_translate' : 0, 
                         'template_use_facsimile' : 0, 
                         'wysiwyg_restricted' : 0
                       }
        if self.template is None or self.template == '':
            self.template = []
        self.template.append( new_template )
        if len(self.template) == 1 or not self.default_template:
            self.default_template = uid

        return 1

    security.declarePublic( 'deleteTemplates' )
    def deleteTemplates( self, template_uids ):
        """
            Delete templates by given template uids list
        """
        if not template_uids: return 0
        
        if type(template_uids) is StringType:
            template_uids=[template_uids]

        for uid in template_uids:
            for i in range( len(self.template) ):
                if uid == self.template[ i ]['uid']:
                    self.template.pop(i)
                    break

        if len(self.template) == 0 and self.default_template:
            self.forbid_free_cookedbody = ''
            self.default_template = ''

        return 1

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setFreeCookedBodyMode' )
    def setFreeCookedBodyMode( self, forbid_free_cookedbody='' ):
        """
            Sets the edit mode for documents of category.
            If "forbid_free_cookedbody" is true, user can not use free cookedbody (without template)
        """
        if self.template:
            self.forbid_free_cookedbody = forbid_free_cookedbody
        else:
            self.forbid_free_cookedbody = ''

    security.declarePublic( 'getFreeCookedBodyMode' )
    def getFreeCookedBodyMode( self ):
        """
            Returns forbid free cookedbody mode for documents of category.
            User can edit text of the document only with predefined category template
        """
        return self.forbid_free_cookedbody

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setReplyToAction' )
    def setReplyToAction( self, reply_to_action=None ):
        """
            Sets the reply to action property.
            Lets to apply reply to action for documents of category.
        """
        setattr( self, 'reply_to_action', reply_to_action )

    security.declarePublic( 'getReplyToAction' )
    def getReplyToAction( self ):
        """
            Returns reply to action property for documents of category.
        """
        return getattr( self, 'reply_to_action', None )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setLockAttachments' )
    def setLockAttachments( self, lock_attachments=None ):
        """
            Sets the lock attachments property.
            Lets to lock attachments included inside documents of category.
        """
        setattr( self, 'lock_attachments', lock_attachments )

    security.declarePublic( 'getLockAttachments' )
    def getLockAttachments( self ):
        """
            Returns lock attachments property for documents of category.
        """
        return getattr( self, 'lock_attachments', None )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setImplementLanguage' )
    def setImplementLanguage( self, implement_language=None ):
        """
            Sets the implement language property.
            Lets to apply language support application methods for documents of category.
        """
        setattr( self, 'implement_language', implement_language )

    security.declarePublic( 'getImplementLanguage' )
    def getImplementLanguage( self ):
        """
            Returns implement language property for documents of category.
        """
        return getattr( self, 'implement_language', None )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setTemplateMode' )
    def setTemplateMode( self, template_uids, template_edit_fields_only, template_use_translate, template_use_facsimile, wysiwyg_restricted ):
        """
            Sets the template properties for documents of category.

            Arguments:

                'template_edit_fields_only' -- string to turn on/off editing only additional fields values

                'template_use_translate' -- string to use translating for cookedbody

                'template_use_facsimile' -- string to use facsimile for cookedbody

                'wysiwyg_restricted' -- restricted WYSIWYG editor
        """
        if not template_uids:
            return 0

        if type(template_uids) is StringType:
            x = [template_uids]
        else:
            x = template_uids

        for n in range(len(x)):
            uid = x[ n ]
            for i in range(len(self.template)):
                if uid != self.template[ i ]['uid']:
                    continue
                self.template[ i ]['template_edit_fields_only'] = ( template_edit_fields_only[ n ] == '1' and 1 or 0 )
                self.template[ i ]['template_use_translate'] = ( template_use_translate[ n ] == '1' and 1 or 0 )
                self.template[ i ]['template_use_facsimile'] = ( template_use_facsimile[ n ] == '1' and 1 or 0 )
                self.template[ i ]['wysiwyg_restricted'] = ( wysiwyg_restricted[ n ] == '1' and 1 or 0 )

        return 1

    security.declarePublic( 'getEditMode' )
    def getEditMode( self, uid=None ):
        """
            Returns the edit mode for documents of category
        """
        return self._getTemplateMode( uid, key='template_edit_fields_only')

    security.declarePublic( 'getTranslateMode' )
    def getTranslateMode( self, uid=None ):
        """
            Returns the translate mode for documents of category
        """
        return self._getTemplateMode( uid, key='template_use_translate')

    security.declarePublic( 'getFacsimileMode' )
    def getFacsimileMode( self, uid=None ):
        """
            Returns the facsimile mode for documents of category
        """
        return self._getTemplateMode( uid, key='template_use_facsimile')

    security.declarePublic( 'getWysiwygRestrictedMode' )
    def getWysiwygRestrictedMode( self, uid=None ):
        """
            Returns the wysiwyg restricted mode for category template
        """
        return self._getTemplateMode( uid, key='wysiwyg_restricted')

    security.declareProtected( CMFCorePermissions.View, '_getTemplateMode' )
    def _getTemplateMode( self, uid=None, key=None ):
        """
            Returns the template key value
        """
        if not uid or not key:
            return None

        for i in range( len(self.template) ):
            if uid == self.template[ i ]['uid']:
                if self.template[ i ].has_key( key ):
                    return self.template[ i ][ key ] == 1 and '1' or ''
                else:
                    return None

        return None

    security.declareProtected( CMFCorePermissions.View, 'applyDocumentTemplate' )
    def applyDocumentTemplate( self, object, selected_template=None ):
        """
            Copies attaches from template document. Fills document with template document text.

            Arguments:

              'object' -- document to be filled with template text and attachments
              'selected_template' -- uid of template document.
        """
        if not selected_template:
            x = self.getDefaultTemplate()
        else:
            x = selected_template
        if x is None:
            return
        tdoc = getObjectByUid(self, x)
        if tdoc is None:
            return
        if tdoc.listAttachments():
            # Copy attachments from template document
            for attach in tdoc.listAttachments():
                object.getVersion()._setObject( attach[0], attach[1]._getCopy(object) )
                object.getVersion().attachments.append( attach[0] )
            # Associate new document with attach if necessary
            if tdoc.associated_with_attach:
                id = tdoc.associated_with_attach
                object.associateWithAttach(id)
        text = getattr(tdoc, 'text', None)
        # Fill new document with template document text
        Document._edit( object, text, text_format='html' )
        # text = tdoc.text
        # object.edit('html', text)
        setattr(object, 'selected_template', x)

    security.declareProtected( CMFCorePermissions.ManagePortal, 'addAttributeDefinition' )
    def addAttributeDefinition( self, name, typ, title='', value='', mandatory=None,
                                read_only=None, hidden=None, sortkey=None, width=None, editable_in_template= None,
                                get_default=None, linked_method=None, options=None ):
        """
            Adds a new field to category - creates new instance of DocumentField class and assigns it to new entry in category "fields" hash.
            Adds new field with "value" value to all objects with cat_id category

            Arguments:

                'name' -- field id

                'typ' -- field type

                'title' -- field title

                'value' -- field default value

                'mandatory' -- if not None, the field is mandatory

                'read_only' -- if not None, the field is read only

                'hidden' -- if not None, the field is hidden

                'sortkey' -- field sortkey

                'width' -- field width.
        """
        if self.getAttributeDefinition( name ):
            raise KeyError, 'Category attribute already exists'

        attr = CategoryAttribute( name, title, typ, mandatory=mandatory, read_only=read_only, hidden=hidden,
                                  sortkey=sortkey, width=width, editable_in_template=editable_in_template,
                                  get_default=get_default, linked_method=linked_method, 
                                  options=options 
                                  )
        
        if typ == 'lines':
            value = list(value)
            attr.setDefaultValue(value)
            if get_default:
                value = value[0]
            else:
                value = None
        elif typ == 'userlist':
            value = None
        else:
            attr.setDefaultValue( value )

        self.attributes._setObject( name, attr )

        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            return

        res = catalog.searchResults( category=self.getId() )

        if not res:
            return

        docs = map( lambda x: x.getObject(), res )
        docs = filter( None, docs )

        for doc in docs:
            doc.setCategoryAttribute( name, value )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'changeAttributeValue' )
    def changeAttributeValue( self, id, value_from=None, value_to=None, reindex=1, REQUEST=None ):
        """
            Changes specified attribute values from the document category.

            Arguments:

                'id' -- Attribute id.

                'value_from' -- From Attribute value (string).

                'value_to' -- To Attribute value (string).
        """
        if id is None:
            return 5

        attr = self.getAttributeDefinition( id )

        if not attr:
            return 4

        attr_type = attr.Type()

        if attr_type in ['boolean','file','userlist','list','link','date','']:
            return 3

        try:
            if attr_type in ['string','text','lines']:
                value_from = str(value_from)
                value_to = str(value_to)
            elif attr_type in ['int']:
                value_from = int(value_from)
                value_to = int(value_to)
            elif attr_type in ['float']:
                value_from = float(value_from)
                value_to = float(value_to)
            else:
                return 3
        except:
            return 1

        catalog = getToolByName(self, 'portal_catalog')
        results = catalog.searchResults( category = self.getId() )
        docs = map( lambda x: x.getObject(), results)
        docs = filter( None, docs)

        IsError = 0

        for doc in docs:
            if value_from != doc.getCategoryAttribute( id ):
                continue
            try:
                doc.setCategoryAttribute( id, value_to, reindex=reindex )
            except:
                IsError = 2
                break

        if not IsError and not reindex:
            catalog.reindexIndex( 'CategoryAttributes', REQUEST )

        return IsError

    security.declareProtected( CMFCorePermissions.ManagePortal, 'copyAttributeValue' )
    def copyAttributeValue( self, id_from=None, id_to=None ):
        """
            Copies specified attributes value from the document category.

            Arguments:

                'id_from' -- From Attribute id.

                'id_to'    -- To Attribute id.
        """
        if id_from is None or id_to is None:
            return 5

        if not self.getAttributeDefinition( id_from ) or not self.getAttributeDefinition( id_to ):
            return 4

        attr_to = self.getAttributeDefinition( id_to )
        attr_to_type = attr_to.Type()

        if attr_to_type in ['boolean','lines','file','userlist','list','link','']:
            return 3

        catalog = getToolByName(self, 'portal_catalog')
        results = catalog.searchResults( category = self.getId() )
        docs = map( lambda x: x.getObject(), results)
        docs = filter( None, docs)

        IsError = 0

        for doc in docs:
            try:
                value_from = doc.getCategoryAttribute( id_from )
                if attr_to_type in ['string','text','date']:
                    value_to = str(value_from)
                elif attr_to_type in ['int']:
                    value_to = int(value_from)
                elif attr_to_type in ['float']:
                    value_to = float(value_from)
                else:
                    continue
            except:
                IsError = 1
                continue

            try:
                doc.setCategoryAttribute( id_to, value_to )
            except:
                IsError = 2
                break

        return IsError

    security.declareProtected( CMFCorePermissions.ManagePortal, 'deleteAttributeDefinitions' )
    def deleteAttributeDefinitions( self, ids ):
        """
            Deletes specified attributes from the document category.

            Arguments:

                'ids' -- List of attribute ids to be removed.
        """
        for id in ids:
            try:
                self.attributes._delObject(id)
            except KeyError:
                pass

        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            return

        results = catalog.searchResults( category = self.getId() )
        objects = map( lambda x: x.getObject(), results)
        objects = filter( None, objects)

        for ob in objects:
            ob.deleteCategoryAttributes(ids)

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setAttributeLinkedMethod' )
    def setAttributeLinkedMethod( self, id, method=None, attribute=None, REQUEST=None ):
        """
            Sets attribute's linked method property
        """
        if id is None:
            return

        attr = self.getAttributeDefinition( id )
        if attr is None:
            return

        attr.setLinkedMethod( method, attribute )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getAttributeLinkedMethod' )
    def getAttributeLinkedMethod( self, id ):
        """
            Returns attribute's linked method property
        """
        if id is None:
            return

        attr = self.getAttributeDefinition( id )
        if attr is None:
            return

        return attr.getLinkedMethod()

    security.declarePublic( 'listAttributeDefinitions' )
    def listAttributeDefinitions( self, sort=None ):
        """
            Returns the list of the document category attributes.

            Result:

              List of CategoryAttribute class instances.
        """
        attributes = self._listAttributeDefinitions()
        for base in self.listBases():
            attributes.extend( base.listAttributeDefinitions() )

        if sort:
            attributes.sort( lambda x, y: cmp(x.Title(), y.Title()) )

        return attributes

    security.declarePublic( 'listAttributeDefinitionsBySortkey' )
    def listAttributeDefinitionsBySortkey( self ):
        """
            Returns the list of the document category attributes sorted by sortkey.

            Result:

              List of CategoryAttribute class instances.
        """
        attrlist = [ ( attr.getSortkey(), attr.getId() ) for attr in self._listAttributeDefinitions() ]
        attrlist.sort()

        attributes = []
        for attr in attrlist:
            attributes.append(self.getAttributeDefinition( attr[1] ))

        for base in self.listBases():
            attributes.extend(base.listAttributeDefinitions())

        return attributes

    security.declarePublic( 'getAttributeDefinitionIds' )
    def getAttributeDefinitionIds( self ):
        """
            Returns the list of the local category attribute ids.

            Result:

              List of CategoryAttribute id.
        """
        return self.attributes.objectIds()

    security.declarePrivate( '_listAttributeDefinitions' )
    def _listAttributeDefinitions( self ):
        """
            Returns the list of the local category attributes.

            Result:

              List of CategoryAttribute class instances.
        """
        return self.attributes.objectValues()

    security.declarePublic( 'getAttributeDefinition' )
    def getAttributeDefinition( self, id, check_name=None ):
        """
            Returns an attribute definition given it's id.

            Arguments:

               'id' -- Attribute id string.

            Result:

               Attribute definition object.
        """
        if not id:
            return None
        if check_name:
            if id.startswith('filter_'):
                id = id[7:]
        for attr in self.listAttributeDefinitions():
            if attr.getId() == id: return attr
        return None

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setAllowedTypes' )
    def setAllowedTypes( self, type_ids ):
        """
            Sets up the list of the portal meta types supported by the category

            Arguments:

                'type_ids' -- list of meta types supported by category

        """
        self.allowed_types = type_ids

    security.declareProtected( CMFCorePermissions.View, 'listAllowedTypes' )
    def listAllowedTypes( self ):
        """
            Returns the list of the portal meta types supported by the category

            Result:

               List of strings.

        """
        return self.allowed_types

    security.declareProtected( CMFCorePermissions.View, 'isTypeAllowed' )
    def isTypeAllowed( self, type_id ):
        """
            Checks whether this category supports the given content type

            Arguments:

                'type_id' -- content type to check
        """
        if getattr( aq_base( type_id ), '_isTypeInformation', None ):
            type_id = type_id.getId()
        return ( type_id in self.allowed_types )

    security.declareProtected( CMFCorePermissions.View, 'getLockTimeout' )
    def getLockTimeout( self ):
        """
            Returns object lock timeout for this category

            Result:

                int, number of seconds
        """
        return self._lock_timeout

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setLockTimeout' )
    def setLockTimeout( self, lock_timeout ):
        """
            Sets lock timeout for category objects

            Arguments:

                'lock_timeout' -- time in seconds

        """
        self._lock_timeout = lock_timeout

    security.declareProtected( CMFCorePermissions.ManagePortal, 'manageAllowSingleStateForVersionArray' )
    def manageAllowSingleStateForVersionArray( self, action, state, transition_for_exclude=None ):
        """
          Manage states where can exists only one version

          Arguments:

            'action' -- action to perform ('add' | 'remove')

            'state' -- state for which perform action

            'transition_for_exclude' -- for action 'add', this mean trasnition by which 'old' version
                                        will be excluded

          Note:

            Are called from workflow.py

        """
        if action=='add':
            self.allow_only_single_version[state]=transition_for_exclude
            self._p_changed = 1
        elif action=='remove' and state in self.allow_only_single_version.keys():
            del self.allow_only_single_version[state]
            self._p_changed = 1

    security.declareProtected( CMFCorePermissions.ManagePortal, 'setBases' )
    def setBases( self, bases ):
        """
            Sets up the list of the category ancestors.

            Arguments:

                'bases' -- List of the CategoryDefinition class instances
                           or ids. All categories already inheriting from the
                           current category are removed from the list.
        """
        old_attrs = self.listAttributeDefinitions()

        # Remove cross-references to avoid infinite recursion.
        valid_bases = []
        permissions = []
        dependent = self.listDependentCategories()

        for base in bases:
            if type( base ) is StringType:
                base = self.getCategoryById( base )

            if base not in dependent:
                valid_bases.append( base.getId() )
                # XXX: fix this
                permissions.extend( base.getWorkflow().permissions )

        self._bases = tuple( valid_bases )

        for cdef in [self,] + self.listDependentCategories():
            wf = cdef.getWorkflow()
            for id in ['states', 'transitions']:
                 wf[id].notifyChanged()

            # Remove nonexisting transitions from states properties.
            states = wf.states
            transitions = wf.transitions
            for state in states.values():
                if states.isPrivateItem( state ):
                    tr_ids = [ tr_id for tr_id in state.getTransitions() if hasattr( transitions, tr_id ) ]
                    state.setProperties( state.title, tr_ids )

        wf = self.getWorkflow()
        # Get initial state from the first ancestor category.
        initial_state = wf.initial_state
        if not (initial_state and wf.states.get( initial_state, None )) and bases:
            base = bases[0]
            if type( base ) is StringType:
                base = self.getCategoryById( base )
            wf.initial_state = base.getWorkflow().initial_state

        if wf:
            # Cleanup workflow data cache
            for id in ['states', 'transitions', 'scripts']:
                 wf[id].notifyChanged()
            wf.permissions = tuple( uniqueValues(permissions) )


        new_attrs = self.listAttributeDefinitions()
        removed_attrs = filter( lambda x, new=new_attrs: x not in new, old_attrs )
        added_attrs = filter( lambda x, old=old_attrs: x not in old, new_attrs )

        catalog = getToolByName(self, 'portal_catalog')
        results = catalog.searchResults( category = self.getId() )

        objects = map( lambda x: x.getObject(), results)
        objects = filter( None, objects )
        for object in objects:
            for attr in added_attrs:
                object.setCategoryAttribute(attr, reindex=0)

            object.deleteCategoryAttributes(removed_attrs)
            object.reindexObject( idxs=['CategoryAttributes'] )

    security.declareProtected( CMFCorePermissions.View, 'listBases' )
    def listBases( self, expand=None ):
        """
            Returns the category ancestors.

            Arguments:

                'expand' -- None value indicates that only first-level bases
                            should be returned, otherwise return the full list
                            of category ancestors.

            Result:

                List of CategoryDefinition class instances.
        """
        bases = [ self.getCategoryById(id) for id in self._bases ]

        if not expand:
            return bases

        results = []
        for base in bases:
            results.append(base)
            results.extend(base.listBases(expand=1))

        return uniqueValues(results)

    security.declareProtected( CMFCorePermissions.View, 'listDependentCategories' )
    def listDependentCategories( self ):
        """
            Lists categories that inherit from the current category.

            Result:

                List of CategoryDefinition class instances.
        """
        result = []
        for cdef in self.listCategories():
            if aq_base(self) in cdef.listBases():
                result.append(cdef)
                result.extend(cdef.listDependentCategories())
        return result

    security.declarePublic('listAttributeOptions')
    def listAttributeOptions( self, typ ):
        """ Returns attribute options list by type
        """
        if typ == 'lines':
            return  ( 'multiple', )
        return None

    security.declareProtected( CMFCorePermissions.View, 'setDefaultRegistry' )
    def setDefaultRegistry( self, registry ):
        if not registry:
            x = None
        elif not isinstance( registry, StringType ):
            x = registry.getUid()
        else:
            x = registry
        self.registry_uid = x

    security.declareProtected( CMFCorePermissions.View, 'getDefaultRegistry' )
    def getDefaultRegistry( self ):
        uid = getattr( self, 'registry_uid', None )
        catalog = getToolByName( self, 'portal_catalog' )
        return uid and catalog.unrestrictedGetObjectByUid( uid )

    security.declareProtected( CMFCorePermissions.View, 'setRN' )
    def setRN( self, RN ):
        self.RN = RN

    security.declareProtected( CMFCorePermissions.View, 'getRN' )
    def getRN( self ):
        return getattr(self, 'RN', None)

    security.declareProtected( CMFCorePermissions.View, 'setRD' )
    def setRD( self, RD ):
        self.RD = RD

    security.declareProtected( CMFCorePermissions.View, 'getRD' )
    def getRD( self ):
        return getattr(self, 'RD', None)

    security.declareProtected( CMFCorePermissions.View, 'setPostfix' )
    def setPostfix( self, postfix ):
        setattr(self, 'postfix', postfix)

    security.declareProtected( CMFCorePermissions.View, 'getPostfix' )
    def getPostfix( self ):
        return getattr(self, 'postfix', '')

InitializeClass( CategoryDefinition )


class CategoryAttribute( Persistent, Implicit ):
    """
        Category attribute class.
        Attributes can store data with types of "string", "boolean", "date", "text", "lines" and other
    """
    _class_version = 1.01

    meta_type = 'Category Attribute'

    security = ClassSecurityInfo()

    _editable_in_template = 1

    get_default = None

    def __init__( self, id, title, typ, default='', mandatory=None,
                  read_only=None, hidden=None, sortkey=None, width=None, editable_in_template=None,
                  get_default=None, linked_method=None, options=None ):

        Persistent.__init__( self )
        self.name = id
        self.title = title
        self.typ = typ
        self.defvalue = default
        self.get_default = get_default
        self.read_only = read_only
        self.hidden = hidden
        self._mandatory = mandatory
        self.sortkey = sortkey
        self.width = width
        self._editable_in_template = editable_in_template
        self.linked_method = linked_method
        self.options = options

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not Persistent._initstate( self, mode ):
            return 0

        if not hasattr(self, '_mandatory'):
            self._mandatory = None
        if hasattr(self, 'obligatory'):
            self._mandatory = self.obligatory
        if not hasattr(self, 'read_only'):
            self.read_only = None
        if not hasattr(self, 'hidden'):
            self.hidden = None
        if getattr(self, 'typ', None) == 'link' and getattr(self, 'defvalue', None):
            if type(self.defvalue) == type('') and self.defvalue[0] not in ['0','1','2']:
                self.defvalue = None

        return 1

    security.declarePublic('getId')
    def getId( self ):
        """
            Returns an attribute id.

            Result:

                String.
        """
        return self.name

    security.declarePublic('Title')
    def Title( self ):
        """
            Returns an attribute title.

            Result:

                String.
        """
        return self.title

    security.declarePublic('Type')
    def Type( self ):
        """
            Returns an attribute type.

            Type value is allowed to be either a 'string', 'boolean', 'date',
            'text' or 'lines'.

            Result:

                String.
        """
        return self.typ

    security.declarePublic('isMandatory')
    def isMandatory( self ):
        """
            Checks whether an attribute is mandatory.

            User must specify all values of mandatory attributes before submitting
            the form.

            Result:

                Boolean.
        """
        return self._mandatory

    security.declareProtected(CMFCorePermissions.ManagePortal, 'setMandatory')
    def setMandatory( self, mandatory=1 ):
        """
            Marks an attribute as mandatory.

            Arguments:

                'mandatory' -- Boolean.
        """
        self._mandatory = mandatory

    security.declarePublic('isReadOnly')
    def isReadOnly( self ):
        """
            Checks whether an attribute is read only.

            Result:

                Boolean.
        """
        return self.read_only

    security.declarePublic('isEditable')
    def isEditable( self ):
        """
            Checks whether an attribute is editable in template.
            Editable attribute is shown on the 'Edit' tab of
            document as input-able field (select, input, textarea
            etc) and allows to change attribute value there.

            Result:

                Boolean.
        """
        return self._editable_in_template

    security.declareProtected(CMFCorePermissions.ManagePortal, 'setEditable')
    def setEditable( self, editable=1 ):
        """
            Marks an attribute to be aditable in template.

            Arguments:

                'mandatory' -- Boolean.
        """
        self._editable_in_template = not not editable

    security.declareProtected(CMFCorePermissions.ManagePortal, 'setHidden')
    def setHidden( self, hidden=1 ):
        """
            Marks an attribute to be hidden.

            Arguments:

                'mandatory' -- Boolean.
        """
        self.hidden = not not hidden

    security.declarePublic('isHidden')
    def isHidden( self ):
        """
            Checks whether an attribute is hidden or not.

            Result:

                Boolean.

        """
        return self.hidden

    security.declareProtected(CMFCorePermissions.ManagePortal, 'setReadOnly')
    def setReadOnly( self, read_only=1 ):
        """
            Marks an attribute as read only.

            Arguments:

                'read_only' -- Boolean.
        """
        self.read_only = read_only

    security.declarePublic('isInCategory')
    def isInCategory( self, category ):
        """
            Checks whether an attribute belongs to a given category.

            Result:

                Boolean.
        """
        return self.aq_inContextOf(category)

    security.declarePublic('setComputedDefault')
    def setComputedDefault( self, get_default ):
        """
            Sets attribute computed default property
        """
        self.get_default = get_default

    security.declarePublic('getComputedDefault')
    def getComputedDefault( self ):
        """
            Returns attribute computed default property (not value!)
        """
        default = self.get_default
        if self.Type() in ( 'lines', 'items', ):
            if default:
                if type(default) not in ( TupleType, ListType ):
                    default = [ default ]
            else:
                return []
        elif self.Type() == 'link':
            if not default:
                pass
            else:
                default = default.split(':')
                if default[0] == '2':
                    default = [ 2, default[1] ]
                else:
                    default = [ 1 ]
        return default or None

    security.declarePublic('haveComputedDefault')
    def haveComputedDefault( self ):
        """
            Checks either attribute has computed default property
        """
        return self.get_default and 1 or 0

    security.declarePublic('setOptions')
    def setOptions( self, options ):
        """ 
            Sets attribute options.

            Arguments:

                'options' -- list, such as ['multiple', ...]
        """
        self.options = options

    security.declarePublic('getOptions')
    def getOptions( self, key=None ):
        """
            Returns attribute options
        """
        options = getattr( self, 'options', None )
        if options:
            pass
        if key:
            try:
                value = key in options and 1 or 0
            except:
                value = None
            return value
        return options or []

    security.declareProtected(CMFCorePermissions.ManagePortal, 'setDefaultValue')
    def setDefaultValue( self, value ):
        """
            Sets default attribute value.

            Result:

                Value can be one of following types: boolean, string, text, int, float, date, lines, items, userlist, link.
        """
        if value and self.Type() == 'string' and self.haveComputedDefault(): 
            def_val = getattr( self, 'defvalue', '' )
            if def_val == value[ :len(def_val) ]:
                return
            defvalue = value

        elif value and self.Type() == 'items': 
            defvalue = []
            new_id = 0

            for x in value:
                if x.find( DELIMETER ) > 0:
                    try:
                        title, id, metadata = x.split( DELIMETER )
                    except:
                        title = id = metadata = None
                    title = title.strip()
                    id = id.strip()
                    metadata = metadata.strip()
                else:
                    title = x
                    new_id += 1
                    id = ('000' + str(new_id))[ -MAX_SIZE_OF_ID : ]
                    metadata = ''
                if id and title:
                    defvalue.append( { 'id' : id, 'title' : title, 'metadata' : metadata } )

        elif self.Type() == 'table':
            defvalue = value and int(value) or 0

        else:
            defvalue = value

        self.defvalue = defvalue

    def getReplyToDefaultValue( self, context ):
        """
            Returns 'Reply To' default attribute value
        """
        if context is None:
            return None

        if self.Type() == 'link':
            return context.getUid()

        return None

    security.declarePublic('getDefaultValue')
    def getDefaultValue( self, id=None, translit=None, disable_settings=None, default_only=None ):
        """
            Returns an attribute default value.

            Arguments:

                'id' -- translate just following values, list

                'translit' -- translitted values for some attr types (items, link)

                'disable_settings' -- boolean, don't implement settings

                'default_only' -- boolean, return default value only, not all possible values

            Result:

                Default attribute value.

            Note:

                If field type is 'lines' then return default attribute value with item 'nonselected'.
        """
        nonselected = 'nonselected'

        try:
            msg = getToolByName( self, 'msg', None )
            lang = msg.get_default_language()
        except AttributeError:
            msg = None
            lang = Config.DefaultLanguage

        if self.Type() == 'date':
            if self.haveComputedDefault():
                return DateTime()

        elif self.Type() == 'string':
            if self.haveComputedDefault():
                def_val = getattr( self, 'defvalue', '' )
                if self.get_default == 1:
                    # Executor phone attribute
                    membership = getToolByName( self, 'portal_membership', None )
                    try:
                        member = membership.getAuthenticatedMember()
                        value = member.getProperty('phone')
                        def_val = ( def_val and def_val + ' ' or '' ) + value
                    except: pass
                return def_val

        elif self.Type() == 'userlist':
            if self.haveComputedDefault():
                return [_getAuthenticatedUser(self).getUserName()]

        elif self.Type() == 'lines':
            defvalue = getattr( self, 'defvalue', [] )
            get_default = self.getComputedDefault()
            title = msg is not None and msg.gettext( nonselected, lang=lang ) or nonselected
            def_val = [ title ]

            if default_only: return def_val

            membership = getToolByName( self, 'portal_membership', None )
            member = membership.getAuthenticatedMember()

            if member is not None and get_default and '2' in get_default:
                company = member.getMemberCompany( mode='id' )
                departments = departmentDictionary.listDepartments( company, sort=1 )
                check_groups = '3' in get_default and not disable_settings and \
                    CheckCustomOption( option='check_groups', member=member )
                res = []

                for item in departments:
                    x = item['id']
                    title = item['title']
                    if check_groups and x:
                        if not member.isMemberOfGroup( x ):
                            continue
                    res.append( title )
                #res.sort()
                def_val.extend( res )
            elif defvalue:
                def_val.extend( defvalue )

            return def_val

        elif self.Type() == 'items':
            defvalue = getattr( self, 'defvalue', [] )
            title = msg is not None and msg.gettext( nonselected, lang=lang ) or nonselected
            def_val = [ { 'id' : nonselected, 'title' : title, 'metadata' : '' } ]

            if default_only: return def_val

            if defvalue:
                def_val.extend( defvalue )

            if id:
                ids = type(id) not in ( TupleType, ListType ) and [ id ] or id
                if ids == [ nonselected ]:
                    ids = None
                values = [ item for item in def_val if ids is None or item['id'] in ids ]
                return values
            if translit:
                return [ '%s %s %s %s %s' % ( item['title'], DELIMETER, item['id'], DELIMETER, item['metadata'] ) \
                    for item in def_val ]

            return def_val

        elif self.Type() == 'link':
            defvalue = getattr( self, 'defvalue', None )
            get_default = self.getComputedDefault()
            link_type = get_default and get_default[0]

            if default_only or not link_type:
                return defvalue

            catalog = getToolByName( self, 'portal_catalog', None )

            if catalog is None:
                return defvalue

            if link_type == 1 and defvalue and not translit:
                if id:
                    def_val = []
                    ids = type(id) not in ( TupleType, ListType ) and [ id ] or id
                else:
                    title = msg is not None and msg.gettext( nonselected, lang=lang ) or nonselected
                    def_val = [ { 'id' : nonselected, 'title' : title, 'uid' : None } ]
                    ids = None

                ob = catalog.unrestrictedGetObjectByUid( defvalue )

                if ob is not None:
                    items = [ ( obj.Title(), obj.getId(), obj.getUid() ) for obj in ob.objectValues() \
                        if obj.implements('isContentStorage') ]
                    items.sort()
                    def_val.extend( [ { 'id' : id, 'title' : title, 'uid' : uid } for title, id, uid in items \
                        if not ids or id in ids ] )

            elif link_type == 2 and not translit:
                if id:
                    def_val = []
                    uid = id
                else:
                    title = msg is not None and msg.gettext( nonselected, lang=lang ) or nonselected
                    def_val = [ { 'id' : nonselected, 'uid' : None, 'title' : title, 'description' : None } ]
                    uid = None

                category = get_default[1]

                if category and uid:
                    def_val.extend( [ x for x in catalog.searchCategoryObjects( category=category ) \
                        if x['uid'] == uid ] )

            else:
                def_val = defvalue

            return def_val

        elif self.Type() == 'table':
            defvalue = getattr( self, 'defvalue', None )
            def_val = { 'count' : defvalue or 0, 'values' : [] }

            return def_val
        
        return getattr( self, 'defvalue', '' )

    security.declareProtected(CMFCorePermissions.ManagePortal, 'setTitle')
    def setTitle( self, title ):
        """
            Sets an attribute title.

            Arguments:

                'title' -- Title of the attribute.
        """
        self.title = title

    security.declarePublic('getSortkey')
    def getSortkey( self ):
        """
            Returns an attribute sortkey.

            Sortkey value is allowed to be a 'string' only.

            Result: String.
        """
        return getattr(self, 'sortkey', None) or '999'

    security.declareProtected(CMFCorePermissions.ManagePortal, 'setSortkey')
    def setSortkey( self, sortkey ):
        """
            Sets an attribute sortkey.

            Arguments:

                'sortkey' -- sortkey of the attribute.
        """
        setattr(self, 'sortkey', sortkey)

    security.declarePublic('getWidth')
    def getWidth( self ):
        """
            Returns an attribute filed width.

            Width value is allowed to be a 'int' only.

            Result: String.
        """
        try:
            w = self.width
            if w == '0' or w == 0 or w is None:
                w = ''
        except:
            w = ''

        return w

    security.declareProtected(CMFCorePermissions.ManagePortal, 'setWidth')
    def setWidth( self, width ):
        """
            Sets an attribute width.

            Arguments:

                'width' -- width of the attribute field (string).
        """
        setattr(self, 'width', width)

    security.declareProtected(CMFCorePermissions.ManagePortal, 'setLinkedMethod')
    def setLinkedMethod( self, method=None, attribute=None ):
        """
            Sets an attribute linked method.

            Arguments:

                'method' -- linked method name

                'attribute' -- linked attribute specification (attribute id).
        """
        value = getattr(self, 'linked_method', None)

        if not method:
            value = []
        elif attribute is not None:
            value = [ method, attribute ]

        setattr(self, 'linked_method', value)

    security.declareProtected(CMFCorePermissions.View, 'getLinkedMethod')
    def getLinkedMethod( self ):
        """
            Returns an attribute linked method.

            Results:

                'linked_method' -- list [ method, attribute ].
        """
        return getattr(self, 'linked_method', None)

    security.declareProtected(CMFCorePermissions.View, 'hasLinkedMethod')
    def hasLinkedMethod( self ):
        """
            Returns true if attribute has a linked method.
        """
        return getattr(self, 'linked_method', None) is not None and 1 or 0

InitializeClass( CategoryAttribute )
