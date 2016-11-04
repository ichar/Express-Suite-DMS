"""
TaskDefinitionFactory class.

Purpose of this class is to have all-in-one-class
function to register new action templates (taskDefinition).

To provide single interface to ask about title, handler types, supported types,
form, controller implementation from instance of TaskDefintionRegistry
(from which have to be inheritanced all other action template's registry classes).

By mark '#change_here#' marked places where are needed to make changes
when needed to add new action template (task definition).

$Id: TaskDefinitionFactory.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 18/09/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from types import ListType, TupleType, DictType, StringType

from Acquisition import Implicit, aq_base, aq_parent
from AccessControl import ClassSecurityInfo

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName

from SimpleObjects import Persistent
from TaskDefinitionFollowup import TaskDefinitionRegistryFollowup
from TaskDefinitionMessage import TaskDefinitionRegistryMessage
from TaskDefinitionActivateVersion import TaskDefinitionRegistryActivateVersion
from TaskDefinitionRouting import TaskDefinitionRegistryRouting
from TaskDefinitionNotification import TaskDefinitionRegistryNotification
from TaskDefinitionSetCategoryAttribute import TaskDefinitionRegistry_SetCategoryAttribute
from TaskDefinitionOfficeRegistration import TaskDefinitionRegistryOfficeRegistration

from Utils import InitializeClass


class TaskDefinitionFactory( Persistent, Implicit ):
    """
        This class have only one instance, in MetadataTool
    """
    security = ClassSecurityInfo()

    _v_taskDefinitionRegistryList = None

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
        """
            Initialize attributes
        """
        if not Persistent._initstate( self, mode ):
            return 0

        return 1

    def _makeTaskDefinitionRegistryList( self ):
        """
            In this method are registered all action templates (instances)
        """
        self._v_taskDefinitionRegistryList = [ \
            TaskDefinitionRegistryFollowup(),
            TaskDefinitionRegistryRouting(),
            TaskDefinitionRegistryOfficeRegistration(),
            TaskDefinitionRegistryMessage(),
            TaskDefinitionRegistryActivateVersion(),
            TaskDefinitionRegistry_SetCategoryAttribute() 
        ]

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getTaskDefinitionTypeList' )
    def getTaskDefinitionTypeList( self, as='' ):
        """
            Returns list of registered action templates.

            Arguments:

                'as' -- format for return, if 'asId:Title', returns as ['id']='title'

            Go over all taskDefintionRegistry and make array of types and titles.

        """
        self._makeTaskDefinitionRegistryList()
        taskDefinitionTypeList = []
        for taskDefinitionRegistry in self._v_taskDefinitionRegistryList:
            taskDefinitionTypeList.extend( taskDefinitionRegistry.getTypeList() )

        if as=='asId:Title':
            ret = {}
            for item in taskDefinitionTypeList:
                ret[item['id']] = item['title']
            return ret

        return taskDefinitionTypeList

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getTaskDefinitionFormByTaskType' )
    def getTaskDefinitionFormByTaskType( self, task_definition_type, taskDefinitionArray=None, mode=None ):
        """
            Returns form for specific task definition type.

            Arguments:

                'task_definition_type' -- type of task definition

                'taskDefinitionArray' -- array of values (if form for 'change')

                'mode' -- mode of show ('add', 'change')

            Result:

                Return html-form for specific task definition.
        """
        controllerImplementation = self._getControllerImplementationByTaskDefinitionType( task_definition_type )
        formImplementation = self._getFormImplementationByTaskDefinitionType( task_definition_type )

        if controllerImplementation == '' or formImplementation == '':
            return '' # this mean error

        if taskDefinitionArray is None: # i.e. action add
            x = controllerImplementation.getEmptyArray()
            x['type'] = task_definition_type
        else:
            x = taskDefinitionArray

        # _mode, for analize in dtml (mode - 'add', 'change')
        x['_mode'] = mode
        return formImplementation.getForm( x )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getTaskDefinitionFormScriptOnSubmit' )
    def getTaskDefinitionFormScriptOnSubmit( self, task_definition_type ):
        """
            Returns java-script fragment for form's onSubmit, for specific task_definition_type.

            Arguments:

                'task_definition_type' -- type of task definition

            Result:

                Java-script fragment for valid form onSubmit.
        """
        formImplementation = self._getFormImplementationByTaskDefinitionType( task_definition_type )
        return formImplementation.getTaskDefinitionFormScriptOnSubmit()

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getTaskDefinitionFormScriptOnLoad' )
    def getTaskDefinitionFormScriptOnLoad( self, task_definition_type, task_definition=None ):
        """
            Returns java-script fragment for form's onLoad, for specific task_definition_type.

            Arguments:

                'task_definition_type' -- task definition type

                'task_definition' -- array of values of task_definition, for initialize
        """
        return ""

    security.declarePublic( 'getTaskDefinitionTypeTitle' )
    def getTaskDefinitionTypeTitle( self, task_definition_type ):
        """
            Returns title of task definition type.

            Arguments:

                'task_definition_type' -- type of task definition
        """
        taskDefinitionRegistry = self._getTaskDefinitionRegistrySupportedTaskDefinitionType( task_definition_type )
        return taskDefinitionRegistry.getTitleByType( task_definition_type )

    security.declarePublic( 'getDtmlNameForInfoByType' )
    def getDtmlNameForInfoByType( self, task_definition_type ):
        """
            Returns dtml name for show form for specific task_definition_type on page 'change_state'.

            Arguments:

                'task_definition_type' -- task definition type
        """
        taskDefinitionRegistry = self._getTaskDefinitionRegistrySupportedTaskDefinitionType( task_definition_type )
        return taskDefinitionRegistry.getDtmlNameForInfoByType( task_definition_type )

    def getTaskDefinitionByRequest( self, task_definition_type, request ):
        """
            Returns specific task definition instance from request.

            Arguments:

                'task_definition_type' -- type of task definition to get

                'request' -- REQUEST

            Result:

                Inherit from 'TaskDefinition' class

            Get specific controller, and from it get instance of model.
        """
        controllerImplementation = self._getControllerImplementationByTaskDefinitionType( task_definition_type )

        if controllerImplementation=='':
            print 'no controller'
            return ''

        return controllerImplementation.getTaskDefinitionByRequest( request )

    def _getControllerImplementationByTaskDefinitionType( self, task_definition_type ):
        """
            Returns class-controller implementation by task definition type.

            Arguments:

                'task_definition_type' -- type of task definition

            Result:

                Inherit from 'TaskDefinitionController' class.
        """
        taskDefinitionRegistry = self._getTaskDefinitionRegistrySupportedTaskDefinitionType( task_definition_type )
        if taskDefinitionRegistry is not None:
            return taskDefinitionRegistry.getControllerImplementation( task_definition_type )
        return ''

    def _getFormImplementationByTaskDefinitionType( self, task_definition_type ):
        """
            Returns class-form implementation by task defintion type.

            Arguments:

                'task_definition_type' -- task of task defintion

            Result:

                Inherit from 'TaskDefinitionForm' class
        """
        taskDefinitionRegistry = self._getTaskDefinitionRegistrySupportedTaskDefinitionType( task_definition_type )
        if taskDefinitionRegistry is not None:
            formImplementation = taskDefinitionRegistry.getFormImplementation( task_definition_type )
            formImplementation.setFactory( self )
            return formImplementation
        return ''

    def _getTaskDefinitionRegistrySupportedTaskDefinitionType( self, task_definition_type ):
        """
            Returns task definition registry class which support specific task_definition_type.

            Arguments:

                'task_definition_type' -- type of task definition

            Result:

                Inherit from 'TaskDefinitionRegistry' class.

        """
        self._makeTaskDefinitionRegistryList()
        for taskDefinitionRegistry in self._v_taskDefinitionRegistryList:
            if taskDefinitionRegistry.areSupportTaskDefinitionType( task_definition_type ):
                return taskDefinitionRegistry
        return None

    def getDtml( self, template_name, **kw ):
        """
            Returns parsed dtml-template.

            Arguments:

                'template_name' -- name of dtml to return

                '**kw' -- additional parameters to dtml

            Result:

                Parsed dtml.
        """
        skins = getToolByName( self, 'portal_skins' )
        template = getattr( aq_base( skins['tasks'] ), template_name, None )
        if template is None:
            raise KeyError, template_name
        template = aq_base( template )
        return template( aq_parent( self ), **kw )

InitializeClass( TaskDefinitionFactory, __version__ )
