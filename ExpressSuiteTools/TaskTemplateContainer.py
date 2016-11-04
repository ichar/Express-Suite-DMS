"""
TaskTemplateContainer and TaskTemplate classes.

TaskTemplate -- is container for TaskDefinition instances,
there is only one TaskDefinition on top, other if is, are included
it top (root) TaskDefintion.

And possible to say that TaskTemplate are same that root TaskDefinition, and
when takes title of TaskTemplate, it will be title of root TaskDefinition

When creating first TaskDefinition, creates TaskTemplate.
When delete root TaskDefinition, will be deleted TaskTemplate

$Id: TaskTemplateContainer.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 18/09/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from Acquisition import Implicit

from SimpleObjects import Persistent
from Utils import InitializeClass


class TaskTemplateContainer( Persistent, Implicit ):
    """
        Class container for TaskTemplate.
        Provide interface for modify contained TaskTemplates (add, change, remove).
    """
    _class_version = 1.00

    def __init__( self ):
        Persistent.__init__( self )

    def _initstate( self, mode ):
        if not Persistent._initstate( self, mode ):
            return 0

        if getattr( self, 'taskTemplates', None ) is None:
            self.taskTemplates = {}
        return 1

    def modify( self, action, taskTemplate ):
        """
            Interface for modifying content

            Arguments:

                'action' -- action to perform ('add_template' | 'change_template' | 'del_template')

                'taskTemplate' -- instance which takes part of action

        """
        if action == 'add_template':
            self.taskTemplates[taskTemplate.id] = taskTemplate
        elif action == 'change_template':
            self.taskTemplates[taskTemplate.id].changeTo( taskTemplate )
        elif action == 'del_template':
            del self.taskTemplates[taskTemplate.id]
        self._p_changed = 1

    def activateTaskTemplate( self, template_id, object, transition ):
        """
            Are main function for activatinf specific action template (TaskTemplate)

            Arguments:

                'template_id' -- template id to activate

                'object' -- object for which will be maden action
        """
        return self.taskTemplates[template_id].__of__(self).activate( object, transition )

    __ac_permissions__ = ( ('View', ('getTaskTemplate',),), )    

    def getTaskTemplate( self, template_id ):
        """
            Returns task template by id.

            Arguments:

                'template_id' -- template id to take.

            Result:

                Returns TaskTemplate instance.
        """
        return self.taskTemplates[ template_id ]

    def getTaskTemplates( self, filter=None ):
        """
            Returns all task templates
        """
        taskTemplates = []
        for template_id in self.taskTemplates.keys():
            if filter is None:
                taskTemplates.append( self.getTaskTemplate( template_id ) )
            elif filter=='have_result_codes' and self.getTaskTemplate(template_id).getResultCodes():
                taskTemplates.append( self.getTaskTemplate( template_id ) )
        return taskTemplates

    def getTaskTemplateIds( self, filter=None ):
        """
            Returns ids of task templates.

            Arguments:

                'filter' -- filtering for task templates, now supported only
                            'have_result_codes', this mean task templates which
                            have result codes

            Result:

                List of ids of action templates.
        """
        ids = []
        if filter=='have_result_codes':
            for template_id in self.taskTemplates.keys():
                if self.getTaskTemplate(template_id).getResultCodes():
                    ids.append( template_id )
        elif filter is None:
            ids = self.taskTemplates.keys()
        return ids

    def getTaskTemplatesAsArray( self, filter=None ):
        """
            Returns task templates as array

            Arguments:

                'filter' -- filter for action templates, now supported 'have_result_codes'
                            this mean task templates which have result codes.

            Result:

                Returns array:
                >>> return = [
                >>>   { "template_id": 'template_id1',
                >>>     "template_title": 'template_title1' },
                >>>    ...
                >>> ]
        """
        taskTemplates = []
        for template_id in self.taskTemplates.keys():
            if filter is None:
                taskTemplates.append( { "template_id": template_id, "template_title": self.taskTemplates[template_id].getTitleRootTaskDefinition() } )
            elif filter=='have_result_codes' and self.getTaskTemplate(template_id).getResultCodes():
                taskTemplates.append( { "template_id": template_id, "template_title": self.taskTemplates[template_id].getTitleRootTaskDefinition() } )
        return taskTemplates

InitializeClass( TaskTemplateContainer )


class TaskTemplate( Persistent, Implicit ):
    """
        Class containing TaskDefinitions (i.e. container)
        Provide interface for modify and activate them
    """
    _class_version = 1.0

    def __init__( self, id, title ):
        Persistent.__init__( self )
        self.id = id
        self.title = ''

    def _initstate( self, mode ):
        if not Persistent._initstate( self, mode ):
            return 0

        if getattr( self, 'taskDefinitions', None ) is None:
            self.taskDefinitions = []
        return 1

    def changeTo( self, taskTemplate ):
        self.title = taskTemplate.title
        self._p_changed = 1

    def toArray( self ):
        """
            Return self values (title, id) as array.

            Result:

                Dictionary:
                >>> return = { "template_title": "template_title1", "template_id": "template_id1" }
                >>>
        """
        array = {}
        array["template_title"] = self.getTitleRootTaskDefinition()
        array["template_id"] = self.id
        return array

    def modify( self, action, taskDefinition ):
        """
            Interface for modifying taskDefintions.

            Arguments:

                'action' -- action to perform ('add_task_definition' | 'change_task_definition' |
                            'delete_task_definition' | 'change_task_definition_title')

                'taskDefinition' -- TaskDefinition instance take part in action
        """
        if action == 'add_task_definition':
            return self.addTaskDefinition( taskDefinition )
        elif action == 'change_task_definition':
            return self.changeTaskDefinition( taskDefinition )
        elif action == 'delete_task_definition':
            return self.deleteTaskDefinition( taskDefinition.id )
        elif action == 'change_task_definition_title':
            return self.changeTaskDefinitionTitle( taskDefinition )
        else:
            print 'unknown action for TaskDefinition modify'
            return ''

    def addTaskDefinition( self, taskDefinition ):
        """
            Adds task definition.

            Arguments:

                'taskDefinition' -- TaskDefinition to add
        """
        taskDefinition.id = self.getUniqueTaskDefinitionId()
        self.taskDefinitions.append(taskDefinition)
        self.changeTaskDefinition( taskDefinition )
        self._p_changed = 1
        return taskDefinition.id

    def changeTaskDefinition( self, taskDefinitionNew ):
        """
            Changes task definition.

            Arguments:

                'taskDefinitionNew' -- new TaskDefinition, have id of existing taskDefinition
        """
        taskDefinitionOld = self.getTaskDefinitionById( taskDefinitionNew.id ).__of__(self)
        taskDefinitionOld.changeTo( taskDefinitionNew )
        self._p_changed = 1
        return taskDefinitionNew.id

    def changeTaskDefinitionTitle( self, taskDefinitionNew ):
        """
            Changes task definition's title.

            Arguments:

                'taskDefinitionNew' -- contain new title
        """
        taskDefinitionOld = self.getTaskDefinitionById( taskDefinitionNew.id )
        taskDefinitionOld.name = taskDefinitionNew.name
        self._p_changed = 1
        return taskDefinitionNew.id

    def deleteTaskDefinition( self, id_task_definition ):
        """
            Deletes task definition.

            Arguments:

                'id_task_definition' -- id task defintion to delete

            Note:

                Also will be deleted all childs (included) task definitions
        """
        # we have to delete all childs also
        taskDefinitionsIdToDel = [ id_task_definition ]
        childs = self.getTaskDefinitionTree( id_task_definition )
        for item in childs:
            taskDefinitionsIdToDel.append( item['id'] )
        taskDefinitionsIdToDel.reverse() # we will be delete from end

        for itemIdToDel in taskDefinitionsIdToDel:
            self.deleteTaskDefinitionItem( itemIdToDel )

        self._p_changed = 1
        return ''

    def getResultCodes( self ):
        """
            Return result codes of task template.

            Result:

                Returns array of result codes, which asking from top TaskDefinition.

                >>> result_codes = (
                >>>    { 'id': 'result_code1', 'title': 'title_result_code1' },
                >>>     ...
                >>> )
        """
        # 1. take top task definition
        taskDefinitionOnTop = self.getTaskDefinitionOnTop()
        if taskDefinitionOnTop is None:
            return None
        # 2. ask task definition for its result codes
        return taskDefinitionOnTop.getResultCodes()

    def deleteTaskDefinitionItem( self, id_task_definition ):
        """
            Delete task definition.

            Arguments:

                'id_task_definition' -- id task definition to delete
        """
        del self.taskDefinitions[ self.getTaskDefinitionPositionById( id_task_definition ) ]

    def getUniqueTaskDefinitionId( self ):
        """
            Gets unique id for task definition.

            Result:

                Returns unique id for task definition.
        """
        ids = []
        for taskDefinition in self.taskDefinitions:
            ids.append( int( taskDefinition.id ) )
        try:
            max_id = max(ids)
        except:
            max_id = 0
        return str( max_id+1 ) # use string as taskDefinition id

    def getTaskDefinitionsOfParent( self, parent_id ):
        """
            Gets included task definition to parent task defintion.

            Arguments:

                'parent_id' -- id of parent's task definition

            Result:

                Array of task definitin which are included to parent's task definition.
        """
        tasks = []
        for taskDefinition in self.taskDefinitions:
            if taskDefinition.parent_id == parent_id:
                tasks.append(taskDefinition)
        return tasks

    def getTaskDefinitionById( self, id_task_definition ):
        """
            Gets task definition by id.

            Arguments:

                'id_task_definition' -- id task definition to take

            Result:

                Returns TaskDefinition.
        """
        for taskDefinition in self.taskDefinitions:
            if taskDefinition.id == id_task_definition:
                return taskDefinition
        return None

    def getTaskDefinitionPositionById( self, id_task_definition ):
        """
            Gets position of TaskDefinition in array.

            Arguments:

                'id_task_definition' -- id task definition
        """
        pos = 0
        for taskDefinition in self.taskDefinitions:
            if taskDefinition.id == id_task_definition:
                return pos
            pos=pos+1
        return None

    def getTaskDefinitionOnTop( self ):
        """
            Gets task definition on top
        """
        taskDefinitions = self.getTaskDefinitionsOfParent( '0' )
        if len( taskDefinitions ) > 1:
            print 'something wrong'
            return None
        elif len( taskDefinitions ) == 1:
            return taskDefinitions[0]
        return None

    # getTaskDefinitionParents
    # returns: parents as array { "id":, "name": }
    def getTaskDefinitionParents( self, id_task_definition ):
        """
            Returns all parents of specified task definition.

            Arguments:

                'id_task_definition' -- id of task definition

            Result:

                Array of task definition which are parents of specified task definition
                >>> return = [
                >>>   { "id": "id1", "name": "name1" },
                >>>   ...
                >>> ]
        """
        parents = []
        parent_id = id_task_definition
        while parent_id != '0':
            if parent_id != id_task_definition:
                taskDefinition = self.getTaskDefinitionById( parent_id ).toArray()
                parent = {}
                parent["id"] = taskDefinition["id"]
                parent["name"] = taskDefinition["name"]
                parents.append( parent )
            # get parent of current taskDefinition
            parent_id = self.getTaskDefinitionById( parent_id ).parent_id
        parents.reverse()
        return parents

    #----[ activate ]----
    def activate( self, object, transition ):
        """
            Activate task template.

            Arguments:

                'object' -- object for which action will be maden

            Activation mean making action, i.e. TaskTemplate may contains
            more that one TaskDefinition - each task definition will be
            activated.
        """
        ret_from_up = { 'task_template_id': self.id } # needed for top-task-definition for 'task_definition_id' attribute
        taskDefinitionOnTop = self.getTaskDefinitionOnTop()
        if taskDefinitionOnTop is None:
            return
        return self.activateTaskDefinition( taskDefinitionOnTop, object, ret_from_up, transition )

    # recursive function
    def activateTaskDefinition( self, taskDefinition, object, ret_from_up, transition ):
        """
            Activating task definition.

            Arguments:

                'taskDefinition' -- TaskDefinition for activate

                'object' -- object for which action will be performed

                'ret_from_up' -- result from previous activating

            Note:

                Recurse function.

            TaskDefinition may have included TaskDefinition - we have to
            activate them aslo.
        """
        ret = taskDefinition.__of__(self).activate( object, ret_from_up, transition )
        # may by add handler here? f.e.
        # if ret['message_to_task_template'] == 'exit':
        #   return
        # i.e. TaskDefinition's "activate" method can pass 'events' to self container - TaskTemplate,
        # by 'ret' array
        # f.e. dinamically creation task definition...
        # or making actions on TaskTemplate level, and pass result to 'ret' array, and
        #    handle them in child's TaskDefinition (where needed)
        # or making logical condition - pass to self.activateTaskDefinition only [0] or [1] child
        # accordingly condition
        #
        for childTaskDefinition in self.getTaskDefinitionsOfParent( taskDefinition.id ):
            self.activateTaskDefinition( childTaskDefinition, object, ret, transition )
        return ret

    def getTaskDefinitionTree( self, parent_id = '0' ):
        """
            Returns all TaskDefinition as tree.

            Arguments:

                'parent_id' -- parents for tree (default '0')

            Result:

                >>> return = [
                >>>  { 'id': 'task_definition_id1', 'level': 'level', 'name': 'name1', 'type': 'type1' }
                >>>  ...
                >>> ]
        """
        taskDefinitionTree = []
        level = 0
        for taskDefinition in self.getTaskDefinitionsOfParent( parent_id ):
            self.getTreeBranch( taskDefinitionTree, level, taskDefinition.id )
        return taskDefinitionTree

    # recursive function
    def getTreeBranch( self, tree, level, parent_id ):
        """
            Return tree branch, for specific parent.

            Arguments:

                'tree' -- tree array which are filled

                'level' -- current level

                'parent_id' -- parent from which needed to take leaves

            Note:

                Recursion function.
        """
        taskDefinition = self.getTaskDefinitionById( parent_id )
        treeItem = {}
        treeItem["id"] = taskDefinition.id
        treeItem["level"] = level
        treeItem["name"] = taskDefinition.name
        treeItem["type"] = taskDefinition.type
        tree.append( treeItem )
        for taskDefinition in self.getTaskDefinitionsOfParent( parent_id ):
            self.getTreeBranch( tree, level+1, taskDefinition.id )

    def getTitleRootTaskDefinition( self ):
        """
            Returns title of root task definitin
        """
        if len( self.getTaskDefinitionsOfParent('0') ) == 1:
            return self.getTaskDefinitionsOfParent('0')[0].name
        return 'n/a'

InitializeClass( TaskTemplate )
