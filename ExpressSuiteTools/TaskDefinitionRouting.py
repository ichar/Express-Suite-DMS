"""
TaskDefinitionRouting class.
Action template for routing document via shortcut or moving to another folder.

$Id: TaskDefinitionRouting.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 18/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import sys
from zLOG import LOG, ERROR, INFO, DEBUG

from types import ListType, TupleType, DictType, StringType
from DateTime import DateTime

from Acquisition import aq_base, aq_inner, aq_parent, aq_get
from OFS.CopySupport import CopyError, eNotSupported, sanity_check

from DepartmentDictionary import departmentDictionary
from Exceptions import SimpleError
from Shortcut import addShortcut
from SearchProfile import addSearchProfile
from TaskDefinitionAbstract import TaskDefinition
from TaskDefinitionAbstract import TaskDefinitionForm
from TaskDefinitionAbstract import TaskDefinitionController
from TaskDefinitionAbstract import TaskDefinitionRegistry
from PortalLogger import portal_log

from Utils import InitializeClass, cookId, getToolByName

from CustomObjects import FolderDepartmentRouting


class TaskDefinitionRouting( TaskDefinition ):
    """
        Document routing on the basis of shortcut and/or relocation between folders
    """
    _class_version = 1.01

    def __init__( self, routing_type='routing_shortcut' ):
        """
            Creates new instance.

            May be 6 types of routing:

                1. Creating shortcut in the specific folder
                2. Creating search profile in the specific folder
                3. Moving document itself to the specific folder
                4. Moving document to the member's folder
                5. Moving document to the department's folder
                6. Moving document to the public catalog
        """
        TaskDefinition.__init__( self )

        self.type = routing_type
        self.dest_folder_uid = None
        self.dest_folder_title = ''
        self.dest_folder_URL = ''
        self.source_attribute = ''
        self._make_subfolders_type = None
        self.to_whom = None
        self.category = None

    def _initstate( self, mode ):
        if getattr( self, '_make_subfolders_type', None ) is None:
            self._make_subfolders_type = None
        if getattr( self, 'to_whom', None ) is None:
            self.to_whom = None
        if getattr( self, 'category', None ) is None:
            self.category = None
        return 1

    def toArray( self, arr=None ):
        """
            Converts object's fields to dictionary.

            Result:

                Dictionary as { 'field_name': 'field_value', ... }
        """
        if arr is None or type(arr) is not DictType:
            x = {}
        else:
            x = arr.copy()
        x = TaskDefinition.toArray( self, x )

        x['dest_folder_uid'] = self.dest_folder_uid
        x['dest_folder_title'] = self.dest_folder_title
        x['dest_folder_URL'] = self.dest_folder_URL
        x['source_attribute'] = getattr( self, 'source_attribute', '' )
        x['_make_subfolders_type'] = getattr( self, '_make_subfolders_type', '' )
        x['to_whom'] = self.to_whom
        x['category'] = self.category

        return x

    def changeTo( self, taskDefinition ):
        """
            Changes self data.

            Changes 'dest_folder_uid' explicitly; 'dest_folder_title' and 'dest_folder_URL' are
            changed according 'dest_folder_uid'.

            Arguments:

                'task_definition' -- instance of TaskDefinition, to which needed to change.
        """
        TaskDefinition.changeTo( self, taskDefinition )
        # specific fields
        self.source_attribute = taskDefinition.source_attribute
        self._make_subfolders_type = taskDefinition._make_subfolders_type
        self.to_whom = taskDefinition.to_whom
        self.category = taskDefinition.category

        uid = taskDefinition.dest_folder_uid
        self.dest_folder_uid = uid and len(uid) > 10 and uid or None

        object = self._unrestrictedGetObjectByUid( self.dest_folder_uid )

        if object is not None:
            self.dest_folder_title = object.title_or_id()
            self.dest_folder_URL = object.absolute_url()
        else:
            self.dest_folder_title = ''
            self.dest_folder_URL = None
            self.dest_folder_uid = None

    def _unrestrictedGetObjectByUid( self, uid=None, id=None ):
        """
            Unrestricted analog for Utils.getObjectByUid().

            Arguments:

                'uid' -- nd_uid of the object we wish to locate
        """
        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None or not uid:
            return None
        if id:
            return catalog.unrestrictedGetSubObjectByUid( uid, id )
        else:
            return catalog.unrestrictedGetObjectByUid( uid )
        return None

    def activate( self, object, ret_from_up, transition ):
        """
            Activate taskDefinition (action template).

            According self.type will be created shortcut in the folder defined
            earlier or object itself will be moved there. There is no need for
            user who changes state of the object to have appropriate
            permissions in destination folder to move object there.

            Arguments:

                'object' -- object in context of which happened activation

                'ret_from_up' -- contains 'task_template_id' key with template definition id (Dictionary)

            Result:

                Also returns dictionary, which is passed to next (inner)
                taskDefinition's activate (if presented).
        """
        if self.type == 'routing_shortcut':
            folder_to_move = self._unrestrictedGetObjectByUid( self.dest_folder_uid )
            if folder_to_move is None:
                raise SimpleError, 'Folder not found'

            shortcut_id = cookId( folder_to_move, id=object.getId() )
            addShortcut(folder_to_move, id=shortcut_id, remote=object)

        elif self.type == 'routing_search_profile':
            folder_to_move = self._unrestrictedGetObjectByUid( self.dest_folder_uid )
            if folder_to_move is None:
                raise SimpleError, 'Folder not found'

            attr_name = self.source_attribute
            attr_value = object.getCategoryAttribute( attr_name )

            if not attr_value:
                return {}

            for x in folder_to_move.objectValues():
                if attr_value == x.Title():
                    return {}

            title = attr_value
            description = ''
            query = { \
                      'category'   : self.category or [],
                      'implements' : 'isHTMLDocument',
                      'sort_on'    : 'modified',
                      'sort_order' : 'reverse',
                      'text'       : title,
                    }

            search_profile_id = cookId( folder_to_move, id=object.getId() )
            addSearchProfile(folder_to_move, id=search_profile_id, title=title, description=description, query=query)

        elif self.type == 'routing_member':
            attr_name = getattr( self, 'to_whom', None )
            to_whom = object.getCategoryAttribute( attr_name )

            portal_log( self, 'TaskDefinitionRouting', 'activate', 'ret_from_up', ( \
                self.type, ret_from_up, attr_name, to_whom ) )

            try:
                membership = getToolByName( self, 'portal_membership', None )
                folder_to_move = membership.getMemberWhomFolder( object, to_whom )
                return self.moveObject( object, folder_to_move )
            except:
                pass

        elif self.type in ( 'routing_department', 'routing_linked_folder', 'routing_object', ):
            attr_name = self.source_attribute
            make_subfolder_type = getattr( self, '_make_subfolders_type', None )
            folder_to_move = None
            folder_ids = None

            portal_log( self, 'TaskDefinitionRouting', 'activate', 'ret_from_up', ( \
                self.type, ret_from_up, attr_name ) )

            #routing via 'department' metadata attribute, defining department's title
            if self.type == 'routing_department':
                attr_value = object.getCategoryAttribute( attr_name )
                department_id = departmentDictionary.getIdByTitle( attr_value )

                if department_id:
                    folder_to_move = self._unrestrictedGetObjectByUid( \
                        uid=self.dest_folder_uid, \
                        id=department_id, \
                        )
                    if folder_to_move is None:
                        # search by catalog, it may be including inside
                        folder_to_move = self.getDepartmentFolder( self.dest_folder_uid, department_id )
                    else:
                        # may be shortcut
                        if folder_to_move and folder_to_move.meta_type == 'Shortcut':
                            folder_to_move = folder_to_move.getObject()
                else:
                    raise SimpleError, 'Department folder is not defined $ title:%s $ error' % attr_value

                portal_log( self, 'TaskDefinitionRouting', 'activate', 'folder_to_move', ( \
                    `folder_to_move`, self.dest_folder_uid ) )

                folder_ids = FolderDepartmentRouting( object, attr_name, transition, ret_from_up, folder_to_move )

                for x in folder_ids:
                    try:
                        if x: 
                            new_folder_to_move = folder_to_move._getOb( x, None )
                            if new_folder_to_move:
                                folder_to_move = new_folder_to_move
                                break
                    except:
                        pass

            #routing via link metadata attribute, defining linked folder's id
            elif self.type == 'routing_linked_folder':
                attr_value = object.getCategoryAttribute( attr_name )
                if type(attr_value) in ( TupleType, ListType ) and len(attr_value) > 1:
                    linked_folder_id = attr_value[0]
                else:
                    linked_folder_id = attr_value

                if linked_folder_id:
                    folder_to_move = self._unrestrictedGetObjectByUid( \
                        uid=self.dest_folder_uid, \
                        id=linked_folder_id, \
                        )
                else:
                    raise SimpleError, 'Linked folder is not defined $ id:%s $ error' % attr_value

            #routing between folders
            else:
                folder_to_move = self._unrestrictedGetObjectByUid( self.dest_folder_uid )

            if make_subfolder_type:
                try:
                    created = object.created()
                    if created is None: created = DateTime()
                except:
                    created = DateTime()
                if make_subfolder_type == 'by_month':
                    s_title = created.strftime('%Y-%m')
                    s_id = s_title.replace('-','')
                elif make_subfolder_type == 'by_day':
                    s_title = created.strftime('%Y-%m-%d')
                    s_id = s_title.replace('-','')
            else:
                s_id = None

            if make_subfolder_type and s_id:
                subfolder = folder_to_move._getOb( s_id, None )
                if subfolder is None:
                    LOG('TaskDefinitionRouting.activate', INFO, 'new subfolder: [%s] in %s' % ( \
                        s_title, folder_to_move.physical_path() ))

                    folder_to_move.manage_addHeading( id=s_id, title=s_title, set_owner=1 )
                    folder_to_move = folder_to_move._getOb( s_id, None )
                else:
                    folder_to_move = subfolder

            return self.moveObject( object, folder_to_move )

        else:
            raise SimpleError, 'Invalid routing type'

        return {}

    def moveObject( self, object, folder_to_move=None ):
        """
            Prepares moving object into new folder
        """
        if folder_to_move is None:
            raise SimpleError, 'Folder not found $ UID:%s-%s $ error' % ( self.dest_folder_uid, object.getUid() )

        dest_id = object.getId()
        dest_path = folder_to_move.physical_path()
        object_path = aq_parent(aq_inner(object)).physical_path()

        #check object current path, if it's located in the destination folder already, return
        if dest_path == object_path:
            return {}

        portal_log( self, 'TaskDefinitionRouting', 'moveObject', 'change location', ( object_path, dest_path ) )

        #if no copies permitted, uncomment this:
        #folder_to_move._checkId( dest_id )
        #code from OFS.CopySupport to prevent security check
        if not self.object_cb_isMoveable( object ):
            raise CopyError, eNotSupported % dest_id

        try:
            object._notifyOfCopyTo( folder_to_move, op=1 )
        except:
            raise CopyError, sys.exc_info()[1]

        if not sanity_check( folder_to_move, object ):
            raise CopyError, 'This object cannot be pasted into itself'

        return { 'should_be_moved' : 1, 'folder_to_move' : folder_to_move }

    def object_cb_isMoveable( self, object ):
        """
            Overrides cb_isMoveable() for the object.
            Does not make ALL necessary checks but here it is not needed.
        """
        # Is object moveable? Returns 0 or 1
        if not (hasattr(object, '_canCopy') and object._canCopy(1)):
            return 0
        if hasattr(object, '_p_jar') and object._p_jar is None:
            return 0
        try: n=aq_parent(aq_inner(object))._reserved_names
        except: n=()

        o_id = object.id
        if callable(object.id): 
            o_id = object.id()

        if o_id in n:
            return 0
        return 1

    def getDepartmentFolder( self, dest_folder_uid=None, id=None ):
        """
            Returns department's folder object
        """
        if not dest_folder_uid or not id:
            return None

        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            return None

        folder_to_move = self._unrestrictedGetObjectByUid( dest_folder_uid )
        if folder_to_move is None:
            return None

        query = {}
        query['path'] = folder_to_move.physical_path() + '%'
        query['implements'] = 'isContentStorage'
        query['id'] = id

        res = catalog.unrestrictedSearch( **query )

        if res and len(res) >= 1:
            folder_to_move = res[0].getObject()
        else:
            return None

        return folder_to_move

InitializeClass( TaskDefinitionRouting )


class TaskDefinitionFormRouting( TaskDefinitionForm ):
    """
        Class view (form)
    """
    def __init__( self, routing_type='routing_shortcut' ):
        TaskDefinitionForm.__init__( self )
        self.routing_type = routing_type

    def getForm( self, taskDefinitionArray ):
        """
            Returns form 'task_definition_routing.dtml'
        """
        form = ''
        form += TaskDefinitionForm.getForm( self, taskDefinitionArray )
        form += self._getDtml( 'task_definition_routing', taskDefinitionArray=taskDefinitionArray, \
                               routing_type=self.routing_type )
        return form

    def getTaskDefinitionFormScriptOnSubmit( self ):
        """
            Returns java-script fragment, to check form's fields on submit
        """
        script = """
        return true;
        """
        return script


class TaskDefinitionControllerRouting( TaskDefinitionController ):
    """
        Class controller
    """
    def __init__( self, routing_type='routing_shortcut' ):
        """
            Constructs instance with selected routing type.
        """
        TaskDefinitionController.__init__( self )
        self.routing_type = routing_type

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

        x['dest_folder_uid'] = None
        x['dest_folder_title'] = ''
        x['source_attribute'] = ''
        x['_make_subfolders_type'] = None
        x['to_whom'] = None
        x['category'] = None

        return x

    def getTaskDefinitionByRequest( self, request ):
        """
            Gets destination folder uid from request and srotes it in TaskDefinitionRouting() instance.
            Returns taskDefinition instance.
        """
        taskDefinition = TaskDefinitionRouting( self.routing_type )
        TaskDefinitionController.getTaskDefinitionByRequest( self, request, taskDefinition )

        if request.has_key('dest_folder_uid'):
            taskDefinition.dest_folder_uid = request['dest_folder_uid']
        if request.has_key('source_attribute'):
            taskDefinition.source_attribute = request['source_attribute']
        if request.has_key('_make_subfolders_type'):
            taskDefinition._make_subfolders_type = request['_make_subfolders_type']
        if request.has_key('to_whom'):
            taskDefinition.to_whom = request['to_whom']
        if request.has_key('category'):
            taskDefinition.category = request['category']

        return taskDefinition


class TaskDefinitionRegistryRouting( TaskDefinitionRegistry ):
    """
        Class that provides information for factory about class
    """
    def __init__( self ):
        TaskDefinitionRegistry.__init__( self )
        self.type_list = [
                      { 'id': 'routing_shortcut',       'title': "Document routing via shortcut"               },
                      { 'id': 'routing_search_profile', 'title': "Document routing via search profile"         },
                      { 'id': 'routing_object',         'title': "Document routing via moving between folders" },
                      { 'id': 'routing_member',         'title': "Move the document to member's folder"        },
                      { 'id': 'routing_department',     'title': "Move the document to department's folder"    },
                      { 'id': 'routing_linked_folder',  'title': "Move the document to the linked folder"      },
        ]

    def getDtmlTokenForInfoByType( self, task_definition_type ):
        """
            The dtml file name is: 'task_definition_%s_info_emb.dtml' % result
        """
        return 'routing'

    def getControllerImplementation( self, task_definition_type ):
        """
            Returns controller implementation

            Arguments:

                'task_definition_type' -- type of action
        """
        return TaskDefinitionControllerRouting( task_definition_type )

    def getFormImplementation( self, task_definition_type ):
        """
            Returns form implementation

            Arguments:

                'task_defintioin_type' -- type of action
        """
        return TaskDefinitionFormRouting( task_definition_type )
