"""
TaskTemplateContainerAdapter class

Purpose of this class is to provide access to inner classes structures (TaskTemplateContainer)
from dtml pages (like interface to dtmls).
Generally this class dont have self logic, but provide security access to logic.

$Id: TaskTemplateContainerAdapter.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 18/09/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from AccessControl import ClassSecurityInfo
from Acquisition import Implicit

from Products.CMFCore import permissions as CMFCorePermissions

from SimpleObjects import Persistent
from Exceptions import DuplicateIdError
from TaskTemplateContainer import TaskTemplate
from Utils import InitializeClass
from Products.CMFCore.utils import getToolByName


class TaskTemplateContainerAdapter( Persistent, Implicit ):

    security = ClassSecurityInfo()

    _v_taskTemplateContainer = None

    def __init__( self ):
        Persistent.__init__( self )

    # CHECK THE OBJECT STATES AND ADVISABLE IGNORE CONFLICT !!!
    # =========================================================
    def _p_resolveConflict( self, oldState, savedState, newState ):
        """
            Try to resolve conflict between container's objects
        """
        return 1

    def _initstate( self, mode ):
        if not Persistent._initstate( self, mode ):
            return 0
        return 1

    def setTaskTemplateContainer( self, taskTemplateContainer ):
        """
            Initialize adapter by TaskTemplateContainer.

            Arguments:

                'taskTemplateContainer' -- instance of TaskTemplateContainer.
        """
        self.taskTemplateContainer = taskTemplateContainer

    def setTaskDefinitionFactory( self, taskDefinitionFactory ):
        """
            Initialize adapter by factory.

            Arguments:

                'taskDefinitionFactory' -- instance of TaskDefinitionFactory.
        """
        self.taskDefinitionFactory = taskDefinitionFactory

    def initTaskTemplateContainerByCategoryId( self, category_id ):
        """
            Initialize TaskTemplateContainer by category id.

            Arguments:

                'category_id' -- id of category
        """
        self._v_taskTemplateContainer = self.getTaskTemplateContainerByCategoryId( category_id )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'makeActionByRequest' )
    def makeActionByRequest( self, category_id, action, request ):
        """
            Make action over task template by request.

            Arguments:

                'category_id' -- id of category

                'action' -- action

                'request' -- REQUEST
        """
        self.initTaskTemplateContainerByCategoryId( category_id )
        taskTemplate = self.getTaskTemplateFromRequest( request )
        self._v_taskTemplateContainer.modify( action, taskTemplate )

        if action == 'del_template':
            self.deleteTemplateIdFromRelatedEntity( taskTemplate.id, category_id )
            ret = ''
        else:
            ret = taskTemplate.id

        return ret

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getTaskTemplatesAsArray' )
    def getTaskTemplatesAsArray( self, category_id, filter=None ):
        """
            Returns list of task templates as array.

            Arguments:

                'category_id' -- id of category
        """
        self.initTaskTemplateContainerByCategoryId( category_id )
        return self._v_taskTemplateContainer.getTaskTemplatesAsArray( filter=filter )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getTaskTemplateById' )
    def getTaskTemplateById( self, category_id, template_id ):
        """
            Returns task template by id (as array).

            Arguments:

                'category_id' -- id of category

                'template_id' -- id of template

            Result:

                Dictionary of task templates fields
        """
        self.initTaskTemplateContainerByCategoryId( category_id )
        return self._v_taskTemplateContainer.getTaskTemplate( template_id ).toArray()

    def getTaskTemplateFromRequest( self, request ):
        """
            Returns TaskTemplate from request.

            Arguments:

                'request' -- REQUEST

            Result:

               Instance of 'TaskTemplate'
        """
        template_id = request['template_id']
        title = 'depricated'  # we dont have this param when action='del_template'
        return TaskTemplate( template_id, title )

    def getTaskTemplateContainerByCategoryId( self, category_id ):
        """
            Returns TaskTemplateContainer by specified category id.

            Arguments:

                'category_id' -- id of category

            Result:

                TaskTemplateContaner of specified category id
        """
        return self._getPortalMetadata().getCategoryById( category_id ).taskTemplateContainer

    def deleteTemplateIdFromRelatedEntity( self, template_id, category_id ):
        """
            Delete 'template_id' from relative entity.

            Arguments:

                'template_id' -- id of action template
        """
        category = self._getPortalMetadata().getCategoryById( category_id )

        # delete from category.transition2TaskTemplate
        for transition_id in category.transition2TaskTemplate.keys():
            try:
                category.transition2TaskTemplate[transition_id].remove(template_id)
                category._p_changed = 1
            except:
                pass

        # detele from category.state2TaskTemplateToDie
        for state_id in category.state2TaskTemplateToDie.keys():
            try:
                del category.state2TaskTemplateToDie[state_id][template_id]
                category._p_changed = 1
            except:
                pass

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getTaskDefinitionTreeItems' )
    def getTaskDefinitionTreeItems( self, category_id, template_id, parent_id = '0' ):
        """
            Returns tree of task definition.

            Arguments:

                'category_id' -- id of category

                'template_id' -- id of action template

                'parent_id' -- id of parent relative of which tree are showed

            Result:

                Array of dictionaries with keys: 'level', 'id_task_definition', 'name', 
                    'task_definition_type_title'
        """
        tree = []
        self.initTaskTemplateContainerByCategoryId( category_id )
        taskDefinitionTree = self._v_taskTemplateContainer.taskTemplates[template_id].getTaskDefinitionTree( parent_id )
        for taskDefinitionTreeItem in taskDefinitionTree:
            treeItem = {}
            treeItem['level'] = taskDefinitionTreeItem['level']
            treeItem['id_task_definition'] = taskDefinitionTreeItem['id']
            task_definition_list = self.taskDefinitionFactory.getTaskDefinitionTypeList('asId:Title')
            task_definition_type_title = task_definition_list[taskDefinitionTreeItem['type']]
            treeItem['name'] = taskDefinitionTreeItem['name']
            treeItem['task_definition_type_title'] = task_definition_type_title
            tree.append( treeItem )
        return tree

    security.declareProtected( CMFCorePermissions.ManagePortal, 'makeTaskDefinitionActionByRequest' )
    def makeTaskDefinitionActionByRequest( self, category_id, action, request ):
        """
            Performs action over task definition by request.

            Arguments:

                'category_id' -- id of category

                'action' -- action to perform ('change_task_definition', 'change_task_definition_title',
                           'delete_task_definition', 'add_task_definition', 'add_root_task_definition')

                'request' -- REQUEST
        """
        self.initTaskTemplateContainerByCategoryId( category_id )
        template_id = request['template_id']
        if action in ('add_task_definition', 'add_root_task_definition') and \
            template_id in self._v_taskTemplateContainer.getTaskTemplateIds():
            raise DuplicateIdError, 'This identifier is already in use.'
        
        redirect_to_list = 0

        # get task definition type
        if action == 'change_task_definition' or action == 'change_task_definition_title' or action == 'delete_task_definition':
            task_definition_type = self.getTaskDefinitionTypeById( category_id, template_id, request['id_task_definition'] )
        elif action == 'add_task_definition':
            task_definition_type = request['task_definition_type']
        elif action == 'add_root_task_definition':
            self.makeActionByRequest( category_id, 'add_template', request )
            request['parent_id']='0'
            task_definition_type = request['task_definition_type']
            action ='add_task_definition'
            redirect_to_list = 1

        taskDefinition = self.taskDefinitionFactory.getTaskDefinitionByRequest( task_definition_type, request )

        ret = self._v_taskTemplateContainer.taskTemplates[template_id].__of__(self._v_taskTemplateContainer).modify( action, taskDefinition )

        if action == 'delete_task_definition' and request['id_task_definition']=='1':
            # main task definition, we have to delete taskTempalte also
            self.makeActionByRequest( category_id, 'del_template', request )

        if redirect_to_list:
            return ''
        return ret

    security.declarePublic( 'getTaskDefinitionById' )
    def getTaskDefinitionById( self, category_id, template_id, id_task_definition ):
        """
            Returns task definition by id.

            Arguments:

                'category_id' -- id of category

                'template_id' -- id of action template

                'id_task_definition' -- id of task definition

            Result:

                TaskDefinition instance.
        """
        try:
            self.initTaskTemplateContainerByCategoryId( category_id )
            return self._v_taskTemplateContainer.taskTemplates[template_id].getTaskDefinitionById( id_task_definition ).toArray()
        except:
            return None

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getTaskDefinitionTypeById' )
    def getTaskDefinitionTypeById( self, category_id, template_id, id_task_definition ):
        """
            Returns type of task definition by id.

            Arguments:

                'category_id' -- id of category

                'template_id' -- id of action template

                'id_task_definition' -- id of task definition

            Result:

                type of task definition (string).
        """
        try:
            self.initTaskTemplateContainerByCategoryId( category_id )
            return self._v_taskTemplateContainer.taskTemplates[template_id].getTaskDefinitionById( id_task_definition ).type
        except:
            return None

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getTaskDefinitionParents' )
    def getTaskDefinitionParents( self, category_id, template_id, id_task_definition ):
        """
            Returns parents of task definition.

            Arguments:

                'category_id' -- id of category

                'template_id' -- id of action template

                'id_task_definition' -- id of task definition

          Result:

              Array of task definition in dictionary format, see TaskTemplate.getTaskDefinitionParents method.
        """
        try:
            self.initTaskTemplateContainerByCategoryId( category_id )
            return self._v_taskTemplateContainer.taskTemplates[ template_id ].getTaskDefinitionParents( id_task_definition )
        except:
            return None

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getTransition2TaskTemplateArray' )
    def getTransition2TaskTemplateArray( self, category_id, transition_id ):
        """
            Returns array of action templates associated with transition.

            Arguments:

                'category_id' -- id of category

                'transition_id' -- id of transition

            Result:

                Array of action templates's id.
        """
        try:
            return \
                self._getPortalMetadata().getCategoryById(category_id).transition2TaskTemplate.has_key(transition_id) \
                and self._getPortalMetadata().getCategoryById(category_id).transition2TaskTemplate[transition_id] \
                or []
        except:
            return None

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getState2TaskTemplateToDieArray' )
    def getState2TaskTemplateToDieArray( self, category_id, state_id ):
        """
            Returns array of action templates which are needed to finalize in specified state.

            Arguments:

                'category_id' -- id of category

                'state_id' -- id of state

            Result:

                Array of id of action templates and result code.
                See MetadataTool.CategoryDefinition.state2TaskTemplateToDie attribute.
        """
        try:
            return \
                self._getPortalMetadata().getCategoryById(category_id).state2TaskTemplateToDie.has_key(state_id) \
                and self._getPortalMetadata().getCategoryById(category_id).state2TaskTemplateToDie[state_id] \
                or []
        except:
            return None

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getState2TaskTemplateToDieMapped' )
    def getState2TaskTemplateToDieMapped( self, category_id, state_id, filter=None ):
        """
            Get array state2task_template_to_die in specific format.

            Arguments:

                'category_id' -- id of category.

                'state_id' -- id of state.

            Result:

                Array of dictionary, with keys:
                'template_id', 'title', 'result_codes', 'finalize', 'result_code'

            Return all task_templates, with list of result codes,
            and with selected (if is) result_code when finalized
            task based on task_template.
        """
        arr = []
        taskTemplateToDie = self._getPortalMetadata().getCategoryById(category_id).state2TaskTemplateToDie.get(state_id, {})
        # taskTemplateToDie = { 'task_template_id1': 'result_code1' , ... }

        self.initTaskTemplateContainerByCategoryId( category_id )
        for taskTemplate in self._v_taskTemplateContainer.getTaskTemplates( filter=filter ):
            item = {
              "template_id": taskTemplate.id,
              "title": taskTemplate.getTitleRootTaskDefinition(),
              "result_codes": taskTemplate.getResultCodes(),
              "finalize": 0,
              "result_code": None,
            }
            if taskTemplate.id in taskTemplateToDie.keys():
                item['finalize'] = 1
                item['result_code'] = taskTemplateToDie[taskTemplate.id]
            arr.append(item)

        return arr

    security.declarePublic( 'getTaskTemplates' )
    def getTaskTemplates( self, category_id, transition_id ):
        """
            Returns array of task templates associated with transition.

            Arguments:

                'category_id' -- id of category

                'transition_id' -- id of transition

            Result:

                Array of dictionaries, with keys: 'template_title', 'template_id'.
        """
        arr = []
        if not self._getPortalMetadata().getCategoryById(category_id).transition2TaskTemplate.has_key( transition_id ):
            return arr
        for task_template_id in self._getPortalMetadata().getCategoryById(category_id).transition2TaskTemplate[transition_id]:
            item = self._getPortalMetadata().getCategoryById(category_id).taskTemplateContainer.getTaskTemplate( task_template_id ).toArray()
            arr.append( item )
        return arr

    security.declareProtected( CMFCorePermissions.ManagePortal, 'callModel' )
    def callModel( self, category_id, function_name, *params ):
        """
            Method to work with 'Resultcodes2TransitionModel' instance methods from dtml.

            Arguments:

                'category_id' -- id of category

                'function_name' -- function name to call

                '*params' -- params to function

            Function-adapter for Resultcodes2TransitionModel called from dtml for access to specific model.
        """
        function_impl = getattr( self._getPortalMetadata().getCategoryById(category_id).resultcodes2TransitionModel, function_name )
        return function_impl( *params )

    def _getPortalMetadata( self ):
        return getToolByName( self, 'portal_metadata', None )

InitializeClass( TaskTemplateContainerAdapter, __version__ )
