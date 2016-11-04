"""
FSFolder class
$Id: FSFolder.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 28/02/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from ntpath import splitext as nt_splitext
import os
import stat

from AccessControl import ClassSecurityInfo
from Acquisition import aq_parent
from DateTime import DateTime

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName

import Config, Features
from FSFile import FSFile
from Heading import Heading
from Utils import cookId, recode_string, translit_string, InitializeClass


factory_type_information = ( { 'id'             : 'FS Folder'
                             , 'meta_type'      : 'FS Folder'
                             , 'title'          : 'File System Folder'
                             , 'description'    : """\
FS Folder objects can be embedded in Portal documents and added to the external sites."""
                             , 'icon'           : 'fs_folder_icon.gif'
                             , 'sort_order'	: 0.8
                             , 'product'        : 'ExpressSuiteTools'
                             , 'factory'        : 'addFSFolder'
                             , 'factory_form'   : 'fs_folder_factory_form'
                             , 'immediate_view' : 'folder'
                             , 'permissions'    : ( CMFCorePermissions.ManagePortal, )
                             , 'allowed_content_types' :
                                ( 'FS Folder',
                                  'FS File',
                                  'Site Image'
                                )
                             , 'actions'        :
                                ( { 'id'            : 'view'
                                  , 'name'          : 'View'
                                  , 'action'        : 'folder'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  , 'category'      : 'folder'
                                  }
                                , { 'id'            : 'metadata'
                                  , 'name'          : 'Metadata'
                                  , 'action'        : 'fs_folder_edit_form'
                                  , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                                  , 'category'      : 'folder'
                                  }
                                )
                             }
                           ,
                           )

def addFSFolder( self, id, path ='', title='', description='', REQUEST=None ):
    """
        Add an FS Folder 
    """
    try:
        tmp_obj = FSFolder( id, path, title, description)
    except OSError, err_obj:
        err_msg = "%s. File: '%s'" % (err_obj.strerror, err_obj.filename)
        raise 'MyOSError', err_msg

    # Add the FSFolder instance to self
    self._setObject(id, tmp_obj)
    if REQUEST is not None:
        return self.folder_contents( self, REQUEST, portal_status_message="Topic added" )


class FSFolder( Heading ):
    """ 
        FS Folder class.
        Objects of this class represent folder in File System (looks like Heading).
    """
    _class_version = 1.00

    meta_type = 'FS Folder'
    portal_type = 'FS Folder'

    __implements__ = ( Heading.__implements__
                     , Features.isFSFolder
                     , Features.isPrincipiaFolderish
                     )

    isCategorial = 0

    _update_needed = None

    security = ClassSecurityInfo()

    def __init__( self,id, path, title='', description='' ):
        """
            Constructs instance of FSFolder.

            Arguments:

                'id' -- Object identifier.

                'path' -- Path in FS to the object we want to wrap.

                'title' -- Optional title.

                'description' -- Optional decription.
        """
        self.description = description
        self._folder_path = os.path.normpath(path)
        Heading.__init__(self, id, title)
        
        st = os.stat( self._folder_path )
        self.creation_date = DateTime(st[stat.ST_MTIME])
        self.modification_date = DateTime(st[stat.ST_MTIME])       
        
        self._update_needed = 1

    def setModificationDate( self, modification_date=None ):
        """
            Sets the date when the resource was last modified.
            When called without an argument, updates date from file in filesystem.
        """
        if modification_date is None:
            self.modification_date = DateTime( os.stat( self._folder_path )[stat.ST_MTIME] )
        else:
            self.modification_date = self._datify(modification_date)

    def modified( self ):
        """
            Dublin Core element - date resource last modified, returned as DateTime
        """
        date = self.modification_date
        if date is None:
            # Upgrade.
            date = DateTime( os.stat( self._folder_path )[stat.ST_MTIME] )
            self.modification_date = date
        return date

    def listObjects( self, REQUEST=None, **kw ):
        """
            Extends Heading.listObjects().
            Besides Heading.listObjects operations, checks if the folder (or any subobject in the folder)
            in FS was changed.
        """
        # Update contents here
        self.checkUpdate()
        return Heading.listObjects( self, REQUEST, **kw )

    def searchObjects( self, REQUEST=None, path_idx=None, **kw ):
        """
            Extends Heading.searchObjects().
            Besides Heading.searchObjects operations, checks if the folder (or any subobject in the folder)
            in FS was changed.
        """
        # Update contents here
        self.checkUpdate()
        return Heading.searchObjects( self, REQUEST, path_idx, **kw )

    def _instance_onCreate( self ):
        """
            Instance creation event hook.
            Extends Heading._instance_onCreate to update the FSFolder contents.
        """
        Heading._instance_onCreate( self )
        self._update_needed = 1
        #Heading.manage_afterAdd( self, item, container )
        self.checkUpdate()

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'edit' )
    def edit( self, path='', title='', description='' ):
        """
            Edits FSFolder properties. Updates FS folder data (filelist, 
            modification date and so on) and reindexes data in the catalog.

            Arguments:

                'path' -- Path in FS to the object we want to wrap.

                'title' -- Optional title.

                'description' -- Optional description.
        """
        if path:
            self._folder_path = os.path.normpath(path)
        self.title = title
        self.description = description
        self.checkUpdate()
        self.reindexObject()
         
    def getOwner( self ):
        """
            Returns owner for this object.
            There is no owner for objects stored in file system.
        """
        return None

    security.declareProtected( CMFCorePermissions.View, 'checkExists' )
    def checkExists( self ):
        """
            Check if folder in FS exists
        """
        if os.path.exists( self._folder_path ):
            return 1
        return 0

    def checkUpdate( self, self_only=None ):
        """
            Checks if object modification time is the same with that of os file.

            Updates size and modification time if the folder in FS was modified.
            If 'self_only' is true, updates only this object's data, not testing subobjects.
            Just sets flag indicating that update is needed.

            Arguments:

                'self_only' -- If true, updates only this object's data, not 
                    does not test subobjects.
        """
        if not self.checkExists():
            #we are no longer exist
            aq_parent(self)._delObject( self.getId() )
            return

        st = os.stat( self._folder_path )
        if DateTime(st[stat.ST_MTIME]) != self.modification_date or self._update_needed:
            self.modification_date = DateTime(st[stat.ST_MTIME])
            if self_only:
                self._update_needed = 1
                return

            paths = {}

            for entry in os.listdir( self._folder_path ):
                try:
                    entry_path = os.path.join( self._folder_path, entry )
                except OSError:
                    continue

                paths[ entry_path ] = entry

            for o_id, object in self.objectItems():
                obj_path = object.getObjectFSPath()
                obj_path_is_dir = 0
                try:
                    obj_path_is_dir = os.path.isdir( obj_path )
                except OSError:
                    pass
                if not object.checkExists() \
                    or ( obj_path_is_dir and object.implements('isFSFile') ) \
                    or ( not obj_path_is_dir and object.implements('isFSFolder') ):
                    self._delObject( o_id )
                else:
                    object.checkUpdate( self_only=1 )
                    try:
                        del paths[ object.getObjectFSPath() ]
                    except KeyError:
                        pass
            
            for path, entry in paths.items():
                try:
                    path_is_dir = os.path.isdir( path )
                except OSError:
                    path_is_dir = 0

                if path_is_dir:
                    #create folder
                    self._createFSObject( path, entry, factory=FSFolder)
                else:
                    #create file
                    self._createFSObject( path, entry, factory=FSFile)

            self._update_needed = None

    def _createFSObject( self, file_path, file_name, factory=FSFile ):
        """
            Creates object of FSFile or FSObject.

            Arguments:

                'file_path' -- Full path to the object in file system.

                'file_name' -- Name of the obejct in file system.

                'factory' -- Class of object to create. May be FSFile or FSFolder.
        """
        msg = getToolByName( self, 'msg', None )
        lang = msg.get_selected_language()
        python_charset = Config.Languages.get(lang)['python_charset']
        sys_charset = Config.Languages.get(lang)['system_charset']

        recoded_fname = recode_string(file_name, enc_from=sys_charset, enc_to=python_charset)
        translit_fname = translit_string(recoded_fname , lang=lang)

        id = cookId(self, translit_fname)
        if factory==FSFile:
            #file
            basename, extension = nt_splitext( recoded_fname )
            while extension and extension[0]=='.':
                extension = extension[1:]

            obj = FSFile(id=id, filepath=file_path, fullname=recoded_fname, title=basename, description='')
            self._setObject(id, obj)

        elif factory==FSFolder:
            #folder
            try:
                obj = FSFolder(id=id, path=file_path, title=recoded_fname)
                self._setObject(id, obj)
            except OSError:
                pass
        else:
            #may be image
            pass

    security.declareProtected( CMFCorePermissions.View, 'getObjectFSPath' )
    def getObjectFSPath( self ):
        """
            Returns the path of the folder in FS
        """
        return self._folder_path 

    security.declareProtected( CMFCorePermissions.AddPortalFolders, 'setPath' )
    def setPath( self, path ):
        """
            Sets the path of the folder in FS
        """
        self._folder_path = path
        self.checkUpdate()
        self.reindexObject()

InitializeClass( FSFolder )
