"""
Action template for activating version ('Make version principal').
It have to be assigned to appropriate transition.

$Id: TaskDefinitionActivateVersion.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 17/06/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from types import ListType, TupleType, DictType, StringType

from TaskDefinitionAbstract import TaskDefinition
from TaskDefinitionAbstract import TaskDefinitionForm
from TaskDefinitionAbstract import TaskDefinitionController
from TaskDefinitionAbstract import TaskDefinitionRegistry


class TaskDefinitionActivateVersion( TaskDefinition ):
    """
        Activate version
    """
    def __init__( self ):
        TaskDefinition.__init__( self )
        self.type = 'activate_version'

    def changeTo( self, taskDefinition ):
        TaskDefinition.changeTo( self, taskDefinition )
        # specific fields
        # none

    def toArray( self, arr={} ):
        if arr is None or type(arr) is not DictType:
            x = {}
        else:
            x = arr.copy()
        x = TaskDefinition.toArray( self, x )
        return x

    def activate( self, object, ret_from_up, transition ):
        object.activateCurrentVersion()
        return {} # there is no passed-to-childs return codes


class TaskDefinitionFormActivateVersion( TaskDefinitionForm ):
    def __init__( self ):
        TaskDefinitionForm.__init__( self )

    def getForm( self, taskDefinitionArray ):
        form = ''
        form += TaskDefinitionForm.getForm( self, taskDefinitionArray )
        form += self._getDtml( 'task_definition_none', taskDefinitionArray=taskDefinitionArray )
        return form


class TaskDefinitionControllerActivateVersion( TaskDefinitionController ):
    def __init__( self ):
        TaskDefinitionController.__init__( self )

    def getEmptyArray( self, emptyArray={} ):
        x = TaskDefinitionController.getEmptyArray( self, emptyArray )
        return x

    def getTaskDefinitionByRequest( self, request ):
        taskDefinition = TaskDefinitionActivateVersion()
        TaskDefinitionController.getTaskDefinitionByRequest( self, request, taskDefinition )
        return taskDefinition


class TaskDefinitionRegistryActivateVersion( TaskDefinitionRegistry ):
    def __init__( self ):
        TaskDefinitionRegistry.__init__( self )
        self.type_list = [
                      { "id": "activate_version", "title": "Make the version principal" },
        ]

    def getControllerImplementation( self, task_definition_type ):
        return TaskDefinitionControllerActivateVersion()

    def getFormImplementation( self, task_definition_type ):
        return TaskDefinitionFormActivateVersion()

