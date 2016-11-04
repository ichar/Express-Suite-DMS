"""
TaskDefinitionSetCategoryAttribute class.
$Id: TaskDefinitionSetCategoryAttribute.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 17/06/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from types import ListType, TupleType, DictType, StringType
from DateTime import DateTime

from TaskDefinitionAbstract import TaskDefinition
from TaskDefinitionAbstract import TaskDefinitionForm
from TaskDefinitionAbstract import TaskDefinitionController
from TaskDefinitionAbstract import TaskDefinitionRegistry


class TaskDefinition_SetCategoryAttribute( TaskDefinition ):
    """
        Class-model.
        Have field 'message', and action print message to console
    """
    def __init__( self ):
        """
            Define field 'message'
        """
        TaskDefinition.__init__( self )

        self.type = 'set_category_attribute'
        self.attribute_name = ''
        self.attribute_value = ''

    def changeTo( self, taskDefinition ):
        """
            Changes field message to new value.

            Arguments:

                'taskDefinition' -- new instance on TaskDefinitionSetCategoryAttribute,
                                    to which values needed to change self.
        """
        TaskDefinition.changeTo( self, taskDefinition )
        # specific fields
        self.attribute_name = taskDefinition.attribute_name
        self.attribute_value = taskDefinition.attribute_value

    def toArray( self, arr=None ):
        """
            We convert field 'message' to array
        """
        if arr is None or type(arr) is not DictType:
            x = {}
        else:
            x = arr.copy()
        x = TaskDefinition.toArray( self, x )

        x["attribute_name"] = self.attribute_name
        x["attribute_value"] = self.attribute_value

        return x

    def activate( self, object, ret_from_up, transition ):
        """
            Print message to console
        """
        print 'dv before: ', object.getCategoryAttribute(self.attribute_name)

        if self.attribute_value == '{date_now}':
            new_value = self._getDateNow()
        else:
            if len(self.attribute_value.split(':'))==2 and self.attribute_value.split(':')[1]=='date':
                new_value = DateTime( self.attribute_value.split(':')[0] )
            else:
                new_value = self.attribute_value

        object.setCategoryAttribute( self.attribute_name, new_value )

        print 'dv after: ', object.getCategoryAttribute(self.attribute_name)
        return {} # there is no passed-to-childs return codes

    def _getDateNow( self ):
        return DateTime(str(DateTime()).split(' ')[0])


class TaskDefinitionForm_SetCategoryAttribute( TaskDefinitionForm ):
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
        form += self._getDtml( 'task_definition_set_category_attribute', taskDefinitionArray=taskDefinitionArray )
        return form


class TaskDefinitionController_SetCategoryAttribute( TaskDefinitionController ):
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

        x['attribute_name'] = ''
        x['attribute_value'] = '{date_now}'  # <-- default value

        return x

    def getTaskDefinitionByRequest( self, request ):
        """
            Parse request and return instance of model (class TaskDefinitionSetCategoryAttribute)
        """
        taskDefinition = TaskDefinition_SetCategoryAttribute()
        TaskDefinitionController.getTaskDefinitionByRequest( self, request, taskDefinition )
        # fill specific fields from request
        if request.has_key('attribute_name'):
            taskDefinition.attribute_name = request['attribute_name']
        if request.has_key('attribute_value'):
            taskDefinition.attribute_value = request['attribute_value']
        return taskDefinition


class TaskDefinitionRegistry_SetCategoryAttribute( TaskDefinitionRegistry ):
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
                      { "id": "set_category_attribute", "title": "Set category attribute" },
        ]

    def getControllerImplementation( self, task_definition_type ):
        """
            Returns class-controller implementation instance (class TaskDefinitionControllerMessage)
        """
        return TaskDefinitionController_SetCategoryAttribute()

    def getFormImplementation( self, task_definition_type ):
        """
            Returns class-form implementation instance (class TaskDefinitionFormMessage)
        """
        return TaskDefinitionForm_SetCategoryAttribute()
