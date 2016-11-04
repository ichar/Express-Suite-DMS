"""
TaskDefinitionNotification class.
Action template for notification about changing transition of document via email.

$Id: TaskDefinitionNotification.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 18/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from types import ListType, TupleType, DictType, StringType

from Products.CMFCore import permissions as CMFCorePermissions

from TaskDefinitionAbstract import TaskDefinition
from TaskDefinitionAbstract import TaskDefinitionForm
from TaskDefinitionAbstract import TaskDefinitionController
from TaskDefinitionAbstract import TaskDefinitionRegistry

from Utils import InitializeClass, getToolByName


class TaskDefinitionNotification( TaskDefinition ):
    """
        Notification to users about performing transition on the document
    """
    _class_version = 1.00

    def __init__( self, routing_type=None ):
        """
            Creates new instance
        """
        TaskDefinition.__init__( self )
        self.type = 'notification'

    def toArray( self, arr={} ):
        """
            Converts object's fields to dictionary

            Result:

                Dictionary as { 'field_name': 'field_value', ... }
        """
        x = TaskDefinition.toArray( self, arr )
        return x
        
    def activate( self, object, ret_from_up, transition ):
        """
            Activate taskDefinition (action template)

            Send email notifications.

            Arguments:

                'object' -- object in context of which happened activation

                'ret_from_up' -- dictionary

            Result:

                Also returns dictionary, which is passed to next (inner) taskDefinition's activate (if presented).
        """
        return {}

InitializeClass( TaskDefinitionNotification )


class TaskDefinitionFormNotification( TaskDefinitionForm ):
    """
        Class view (form)
    """
    def getForm( self, taskDefinitionArray ):
        """
            Returns form 'task_definition_notification.dtml'
        """
        form = ''
        form += TaskDefinitionForm.getForm( self, taskDefinitionArray )
        form += self._getDtml( 'task_definition_notification', taskDefinitionArray=taskDefinitionArray )
        return form


class TaskDefinitionControllerNotification( TaskDefinitionController ):
    """
        Class controller
    """
    def getEmptyArray( self, emptyArray={} ):
        """
            Returns dictionary with empty values.

            Arguments:

                'emptyArray' -- dictionary to fill
        """
        x = TaskDefinitionController.getEmptyArray( self, emptyArray )
        return x

    def getTaskDefinitionByRequest( self, request ):
        """
            Gets destination folder uid from request and srotes it in
            TaskDefinitionNotification() instance.
        """
        taskDefinition = TaskDefinitionNotification( )
        TaskDefinitionController.getTaskDefinitionByRequest( self, request, taskDefinition )

        return taskDefinition


class TaskDefinitionRegistryNotification( TaskDefinitionRegistry ):
    """
        Class that provides information for factory about class
    """
    def __init__( self ):
        """
            Creates new instance
        """
        TaskDefinitionRegistry.__init__( self )
        self.type_list = [ { "id": "notification", "title": "Send notification about transition perform" }, ]

    def getDtmlTokenForInfoByType( self, task_definition_type ):
        """
            The dtml file name is: 'task_definition_%s_info_emb.dtml' % result
        """
        return 'notification'

    def getControllerImplementation( self, task_definition_type ):
        """
            Returns controller implementation.

            Arguments:

                'task_definition_type' -- type of action.
        """
        return TaskDefinitionControllerNotification()

    def getFormImplementation( self, task_definition_type ):
        """
            Returns form implementation.

            Arguments:

                'task_defintioin_type' -- type of action.

            Note:

                Abstract method.
        """
        return TaskDefinitionFormNotification()
