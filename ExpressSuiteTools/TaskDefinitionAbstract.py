"""
TaskDefinition abstract classes.

It consist of:
    -- model (TaskDefinition)
    -- controller (TaskDefinitionController)
    -- view (TaskDefinitionForm)
    -- register (TaskDefinitionRegistry)

Them provide bases functions.

Model - store fields, and have function for activate
Controller - takes information from form and change model
View - showing model
Register - registration of action template (task definition) in factory (TaskDefinitionFactory)

$Id: TaskDefinitionAbstract.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 18/09/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from zLOG import LOG, ERROR, INFO
from types import ListType, TupleType, DictType, StringType
from DateTime import DateTime

from Acquisition import Implicit

from SimpleObjects import Persistent
from Utils import InitializeClass


class TaskDefinition( Persistent, Implicit ):
    """
        Abstract class-model
    """
    _class_version = 1.00

    def __init__( self ):
        Persistent.__init__( self )
        self.id = ''
        self.parent_id = ''
        self.name = ''
        self.type = ''

    # CHECK THE OBJECT STATES AND ADVISABLE IGNORE CONFLICT !!!
    # =========================================================
    def _p_resolveConflict( self, oldState, savedState, newState ):
        """
            Try to resolve conflict between container's objects
        """
        return 1

    def changeTo( self, task_definition ):
        """
            Changes self values to new.

            Arguments:

                'task_definition' -- instance of TaskDefinition, to which needed to change
        """
        self.name = task_definition.name

    def toArray( self, arr=None ):
        """
            Returns self values as array

            Arguments:

                'arr' -- array to which added new values
        """
        if arr is None or type(arr) is not DictType:
            x = {}
        else:
            x = arr.copy()

        x['id'] = self.id
        x['parent_id'] = self.parent_id
        x['name'] = self.name
        x['type'] = self.type

        return x

    def amIonTop( self ):
        """
            Checks whether taskDefinition are on top.

            Result:

                Boolean
        """
        return self.parent_id == '0'

    def activate( self, object, ret_from_up, transition ):
        """
            Activate taskDefinition (action template).

            Arguments:

                'object' -- object in context of which happened activation

                'ret_from_up' -- dictionary

            Result:

                Also return dictionary, which pass to next (inner)
                taskDefinition's activate (if is)
        """
        pass

    def getResultCodes( self ):
        """
            Return result codes

            Result:

                Return array of result codes
        """
        return []

InitializeClass( TaskDefinition )


class TaskDefinitionForm:
    """
        Class view (form)
    """
    def __init__( self ):
        pass

    def setFactory( self, factory ):
        """
            Initialization by factory.

            Arguments:

                'factory' -- instance of factory (TaskDefinitionFactory)
        """
        self.factory = factory

    def _getDtml( self, dtml_template_id, **kw ):
        """
            Returns dtml.

            Arguments:

                'dtml_template_id' -- dtml-template to parse

                '**kw' -- additional arguments

            Get dtml, parse and return result.
        """
        return self.factory.getDtml( dtml_template_id, **kw )

    def getForm( self, taskDefinitionArray ):
        """
            Returns form (html)

            Arguments:

                'taskDefinitionArray' -- dictionary with values, which will be showed on form
        """
        return self._getDtml( 'task_definition', taskDefinitionArray=taskDefinitionArray )

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


class TaskDefinitionController:
    """
      Class controller
    """

    def __init__( self ):
        pass

    def getTaskDefinitionByRequest( self, request, taskDefinition ):
        """
            Returns taskDefinition instance (model) by request.

            Arguments:

                'request' -- REQUEST

                'taskDefiniton' -- instance from upper instance of TaskDefinitionController
        """
        if request.has_key('name'): # action del
            taskDefinition.name = request['name']

        if request.has_key('parent_id'): # action add or del
            taskDefinition.parent_id = request['parent_id']

        if request.has_key('id_task_definition'): # action change or del
            taskDefinition.id = request['id_task_definition']

    def getEmptyArray( self, empty_array=None ):
        """
            Returns array with empty values.

            Arguments:

                'empty_array' -- array to fill
        """
        if empty_array is None or type(empty_array) is not DictType:
            x = {}
        else:
            x = empty_array.copy()

        x['name'] = ''

        return x


class TaskDefinitionRegistry:
    """
        Class provided information for factory about class
    """
    def __init__( self ):
        self.type_list = []

    def getTypeList( self ):
        """
            Returns list of handled action-types.

            Return [{ "id": "id1", "title": "title1" }, ... ]
            "id" have to be unique for all task definitions
        """
        return self.type_list

    def getTitleByType( self, type ):
        """
            Returns title of action definition by type.

            Arguments:

                'type' -- type of action
        """
        for type_item in self.type_list:
            if type_item['id']==type:
                return type_item['title']
        return ''

    def areSupportTaskDefinitionType( self, task_definition_type ):
        """
            Checks whether this taskDefinition (action template) support specific type.

            Arguments:

                'task_definition_type' -- type to check

            Result:

                Boolean, true if supported, fasle - not
        """
        supported_ids = self._getTypeListAsIds()
        return ( task_definition_type in supported_ids )

    def getDtmlNameForInfoByType( self, task_definition_type ):
        """
            Returns dtml name, for showing of page 'change_state'.

            Arguments:

                'task_definition_type' -- showing type

            Result:

                Dtml-file name

            On page 'change_state' user can see action templates which
            will be activated, and also user can change some fields of them.

            The dtml file name are: 'task_definition_%s_info_emb.dtml' % self.getDtmlTokenForInfoByType
        """
        if self.getDtmlTokenForInfoByType( task_definition_type ):
            return 'task_definition_%s_info_emb' % self.getDtmlTokenForInfoByType( task_definition_type )
        return None

    def getDtmlTokenForInfoByType( self, task_definition_type ):
        """
            Get 'token' for making full dtml-file-name, by mehod 'getDtmlNameForInfoByType'.

            Arguments:

                'task_definition_type' -- action type

            Note:

                Overwrite in inheritance classes, if needed
        """
        # overwrite in classes for have dtml for info on page 'change_state'
        return None

    def getControllerImplementation( self, task_definition_type ):
        """
            Returns controller implementation.

            Arguments:

                'task_definition_type' -- type of action

            Note:

                Abstract method
        """
        pass

    def getFormImplementation( self, task_definition_type ):
        """
            Returns form implementation.

            Arguments:

                'task_defintioin_type' -- type of action

            Note:

                Abstract method
        """
        pass

    def _getTypeListAsIds( self ):
        ids = []
        for item in self.type_list:
            ids.append( item['id'] )
        return ids
