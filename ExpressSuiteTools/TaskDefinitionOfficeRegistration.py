"""
Action template for running office registration procedure.

Purpose of this class is to activate registration action for a document.
Registration is a procedure of creating new registry entry.

Registry and roles according which we create the entry defined automatically.

$Id: TaskDefinitionOfficeRegistration.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 26/02/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import sys
from types import ListType, TupleType, DictType, StringType

from Acquisition import aq_base, aq_inner, aq_parent

from Exceptions import SimpleError
from TaskDefinitionAbstract import TaskDefinition
from TaskDefinitionAbstract import TaskDefinitionForm
from TaskDefinitionAbstract import TaskDefinitionController
from TaskDefinitionAbstract import TaskDefinitionRegistry
from PortalLogger import portal_log

from Utils import InitializeClass, getToolByName

from CustomObjects import ObjectHasCustomCategory, IsPrivateObject, CustomDefs


class TaskDefinitionOfficeRegistration( TaskDefinition ):
    """
        Office regisration action class
    """
    _class_version = 1.00

    def __init__( self, registration_type='auto' ):
        """
            Creates new instance
        """
        TaskDefinition.__init__( self )

        self.type = registration_type
        self.registry_uid = None
        self.registry_description = None
        self.registry_URL = None
        self.mask = ''
        self.default_category = None
        self.current_registry = 1
        self.private_only = None
        self.activate_action = None

    def changeTo( self, taskDefinition ):
        """
            Changes self values to new.

            Arguments:

                'task_definition' -- instance of TaskDefinition, to which needed to change
        """
        TaskDefinition.changeTo( self, taskDefinition )
        # specific fields
        self.mask = taskDefinition.mask
        self.default_category = taskDefinition.default_category
        self.current_registry = taskDefinition.current_registry
        self.private_only = taskDefinition.private_only
        self.activate_action = taskDefinition.activate_action

        object = self._unrestrictedGetRegistryObject()
        if not object:
            return

        self.registry_uid = object.getUid()
        self.registry_description = object.Description()
        self.registry_URL = object.absolute_url()

    def _unrestrictedGetRegistryObject( self ):
        """
            Search a registry object according task properties
        """
        catalog = getToolByName( self, 'portal_catalog' )
        if catalog is None:
            return None

        results = catalog.searchRegistries( current_registry=self.current_registry )
        registry = None

        for x in results:
            obj = x.getObject()
            if not x['id'].startswith( self.mask ):
                continue
            if obj.getDefaultCategory() != self.default_category:
                continue
            registry = obj
            break

        portal_log( self, 'TaskDefinitionOfficeRegistration', '_unrestrictedGetRegistryObject', 'registry', `registry` )
        return registry

    def toArray( self, arr=None ):
        """
            Returns self values as array.

            Arguments:

                'arr' -- array to which added new values
        """
        if arr is None or type(arr) is not DictType:
            x = {}
        else:
            x = arr.copy()
        x = TaskDefinition.toArray( self, x )

        # specific fields
        x['registry_uid'] = self.registry_uid
        x['registry_description'] = self.registry_description
        x['registry_URL'] = self.registry_URL
        x['mask'] = self.mask
        x['default_category'] = self.default_category
        x['current_registry'] = self.current_registry
        x['private_only'] = self.private_only
        x['activate_action'] = getattr(self, 'activate_action', None)

        return x

    def activate( self, object, ret_from_up, transition ):
        """
            Activate taskDefinition (action template).

            According self.type will be generated an entry in the corresponding registry object.

            Arguments:

                'object' -- object in context of which happened activation

                'ret_from_up' -- contains 'task_template_id' key with template definition id (Dictionary)

            Result:

                Also return dictionary, which pass to next (inner)
                taskDefinition's activate (if is).
        """
        portal_log( self, 'TaskDefinitionOfficeRegistration', 'activate', 'start', self.type )
        if object is None:
            return None
        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            return None

        uid = object.getUid()
        source = catalog.unrestrictedGetObjectByUid( uid ) or object
        IsRegistered = None
        action = {}

        if self.type == 'auto' and source is not None:
            if source.implements('isDocument'):
                if source.registry_ids():
                    action['action'] = self.activate_action
                    return action
                else:
                    IsRun = 1
            else:
                return None
            if self.private_only:
                IsRun = IsPrivateObject( object ) and 1 or 0
            if not IsRun:
                return None
            registry = self._unrestrictedGetRegistryObject()
            if not registry:
                return None

            IsRegistered = registry.DocumentAutoRegistration( source )
            if IsRegistered:
                action['action'] = self.activate_action
            portal_log( self, 'TaskDefinitionOfficeRegistration', 'activate', 'auto', ( IsRegistered, action, `source` ) )

        return action

InitializeClass( TaskDefinitionOfficeRegistration )


class TaskDefinitionFormOfficeRegistration( TaskDefinitionForm ):
    """
        Class view (form)
    """
    def __init__( self, registration_type='auto' ):
        TaskDefinitionForm.__init__( self )
        self.registration_type = registration_type

    def getForm( self, taskDefinitionArray ):
        """
            Returns form (task_definition_office_registration.dtml).
        """
        form = ''
        form += TaskDefinitionForm.getForm( self, taskDefinitionArray )
        form += self._getDtml( 'task_definition_office_registration', taskDefinitionArray=taskDefinitionArray, registration_type=self.registration_type )
        return form

    def getTaskDefinitionFormScriptOnSubmit( self, script='' ):
        """
            Returns javascript-fragment for validation form on submit

            Arguments:

                'script' -- initial value to add
        """
        return ''
        #if (! window.document.getElementsByName('name')[0].value) {
        #    alert('Please specify task definition name');
        #    return false;
        #}


class TaskDefinitionControllerOfficeRegistration( TaskDefinitionController ):
    """
        Class controller
    """
    def __init__( self, registration_type='auto' ):
        """
            Constructs instance with selected office registration type.
        """
        TaskDefinitionController.__init__( self )
        self.registration_type = registration_type

    def getEmptyArray( self, emptyArray=None ):
        """
            Returns dictionary with empty values.

            Arguments:

                'emptyArray' -- dictionary to fill
        """
        if emptyArray is None or type(emptyArray) is not DictType:
            x = {}
        else:
            x = emptyArray.copy()
        x = TaskDefinitionController.getEmptyArray( self, x )

        x['mask'] = None
        x['default_category'] = None
        x['current_registry'] = 1
        x['private_only'] = None
        x['activate_action'] = None

        return x

    def getTaskDefinitionByRequest( self, request ):
        """
            Gets destination folder uid from request and srotes it in
            TaskDefinitionOfficeRegistration() instance.

            Returns taskDefinition instance.
        """
        taskDefinition = TaskDefinitionOfficeRegistration( self.registration_type )
        TaskDefinitionController.getTaskDefinitionByRequest( self, request, taskDefinition )

        if request.has_key('mask'):
            taskDefinition.mask = request['mask']
        if request.has_key('default_category'):
            taskDefinition.default_category = request['default_category']
        if request.has_key('current_registry'):
            taskDefinition.current_registry = request['current_registry']
        if request.has_key('private_only'):
            taskDefinition.private_only = request['private_only']
        if request.has_key('activate_action'):
            taskDefinition.activate_action = request['activate_action']

        return taskDefinition


class TaskDefinitionRegistryOfficeRegistration( TaskDefinitionRegistry ):
    """
        Class provided information for factory about class
    """
    def __init__( self ):
        TaskDefinitionRegistry.__init__( self )
        self.type_list = [ \
                      { 'id' : 'auto', 'title' : 'Document office auto registration' }, \
        ]

    def getDtmlTokenForInfoByType( self, task_definition_type ):
        """
            Get 'token' for making full dtml-file-name, by mehod 'getDtmlNameForInfoByType'.

            Arguments:

                'task_definition_type' -- action type

            Note:

                Overwrite in inheritance classes, if needed
        """
        # overwrite in classes for have dtml for info on page 'change_state'
        return 'office_registration'

    def getControllerImplementation( self, task_definition_type ):
        """
            Returns controller implementation.

            Arguments:

                'task_definition_type' -- type of action
        """
        return TaskDefinitionControllerOfficeRegistration( task_definition_type )

    def getFormImplementation( self, task_definition_type ):
        """
            Returns form implementation

            Arguments:

                'task_defintioin_type' -- type of action
        """
        return TaskDefinitionFormOfficeRegistration( task_definition_type )
