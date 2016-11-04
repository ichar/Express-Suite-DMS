"""
  TaskDefinitionMessage class.

  This is example class. It show example of creation simple action template.
  This action template have only one field: 'message'.
  And simple action: print message to console.

$Id: TaskDefinitionMessage.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 17/06/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from types import ListType, TupleType, DictType, StringType

from TaskDefinitionAbstract import TaskDefinition
from TaskDefinitionAbstract import TaskDefinitionForm
from TaskDefinitionAbstract import TaskDefinitionController
from TaskDefinitionAbstract import TaskDefinitionRegistry


class TaskDefinitionMessage( TaskDefinition ):
    """
        Class-model.
        Have field 'message' and action print message to console.
    """
    def __init__( self ):
        """
            Define field 'message'
        """
        TaskDefinition.__init__( self )
        self.type = 'message'
        self.message = ''

    def changeTo( self, taskDefinition ):
        """
            Changes field message to new value.

            Arguments:

              'taskDefinition' -- new instance on TaskDefinitionMessage, 
                                  to which values needed to change self.
        """
        TaskDefinition.changeTo( self, taskDefinition )
        # specific fields
        self.message = taskDefinition.message

    def toArray( self, arr={} ):
        """
            We convert field 'message' to array
        """
        if arr is None or type(arr) is not DictType:
            x = {}
        else:
            x = arr.copy()
        x = TaskDefinition.toArray( self, x )

        x['message'] = self.message

        return x

    def activate( self, object, ret_from_up, transition ):
        """
            Print message to console
        """
        print 'message: ' + self.message
        return {} # there is no passed-to-childs return codes


class TaskDefinitionFormMessage( TaskDefinitionForm ):
    """
        Class-view, define form for editing model's content (field 'message')
    """
    def __init__( self ):
        TaskDefinitionForm.__init__( self )

    def getForm( self, taskDefinitionArray ):
        """
            Returns form 'task_definition_message.dtml'
        """
        form = ''
        form += TaskDefinitionForm.getForm( self, taskDefinitionArray )
        form += self._getDtml( 'task_definition_message', taskDefinitionArray=taskDefinitionArray )
        return form


class TaskDefinitionControllerMessage( TaskDefinitionController ):
    """
        Class-controller, handle fields from form, and store them to model
    """
    def __init__( self ):
        TaskDefinitionController.__init__( self )

    def getEmptyArray( self, emptyArray={} ):
        """
            Returns empty array (field 'message')
        """
        if emptyArray is None or type(emptyArray) is not DictType:
            x = {}
        else:
            x = emptyArray.copy()
        x = TaskDefinitionController.getEmptyArray( self, x )

        x['message'] = ''

        return x

    def getTaskDefinitionByRequest( self, request ):
        """
            Parse request and return instance of model (class TaskDefinitionMessage)
        """
        taskDefinition = TaskDefinitionMessage()
        TaskDefinitionController.getTaskDefinitionByRequest( self, request, taskDefinition )
        # fill specific fields from request
        if request.has_key('message'):
            taskDefinition.message = request['message']
        return taskDefinition


class TaskDefinitionRegistryMessage( TaskDefinitionRegistry ):
    """
        Class-registry, for registration this action template (task definition)
        in factory. Define supported types.
    """
    def __init__( self ):
        """
            Initialize self.type_list, which store 'id' and 'title' of supported types
        """
        TaskDefinitionRegistry.__init__( self )
        self.type_list = [
                      { "id": "message", "title": "Print message to console" },
        ]

    def getDtmlTokenForInfoByType( self, task_definition_type ):
        """
            Return token for showing form on page 'change_state' where
            possible to change value of assigned to transition action templates
        """
        # in case if this function dont be,
        # on page change_state, will be showing only type and name, dont content of fields
        # (which are showing by dtml, which making in function
        #  getDtmlNameForInfoByType of TaskDefinitionRegistry by this token)
        return 'message'

    def getControllerImplementation( self, task_definition_type ):
        """
            Returns class-controller implementation instance (class TaskDefinitionControllerMessage)
        """
        return TaskDefinitionControllerMessage()

    def getFormImplementation( self, task_definition_type ):
        """
            Returns class-form implementation instance (class TaskDefinitionFormMessage)
        """
        return TaskDefinitionFormMessage()

