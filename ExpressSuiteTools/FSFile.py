"""
FSFile class
$Id: FSFile.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 04/03/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import os
import stat

from ntpath import splitext as nt_splitext
from cStringIO import StringIO

from AccessControl import ClassSecurityInfo
from DateTime.DateTime import DateTime
from OFS.content_types import guess_content_type
from ZPublisher.HTTPRequest import FileUpload

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName

import Config
import Features
from SecureImports import cookId
from SimpleObjects import ContentBase
from Utils import InitializeClass, recode_string

factory_type_information = ( { 'id'             : 'FS File'
                             , 'meta_type'      : 'FS File'
                             , 'title'          : 'File System File'
                             , 'description'    : """\
FS Files can be embedded in FS Folders."""
                             , 'icon'           : 'fs_file.gif'
                             , 'sort_order'     : 0.8
                             , 'product'        : 'ExpressSuiteTools'
                             , 'factory'        : 'addFSFile'
                             , 'immediate_view' : 'metadata_edit_form'
                             , 'permissions'    : ( CMFCorePermissions.ManagePortal, )
                             , 'condition'      : 'python: 1 == 0'
                             , 'actions'        :
                                ( { 'id'            : 'view'
                                  , 'name'          : 'View'
                                  , 'action'        : 'fs_file_view'
                                  , 'permissions'   : (
                                      CMFCorePermissions.View, )
                                  }
                                , { 'id'            : 'metadata'
                                  , 'name'          : 'Metadata'
                                  , 'action'        : 'metadata_edit_form'
                                  , 'permissions'   : (
                                      CMFCorePermissions.ModifyPortalContent, )
                                  }
                                )
                             }
                           ,
                           )

def addFSFile( self, id, filepath, fullname, title = '', description = '' ):
    """
        Adds a File System File
    """
    temp_obj = FSFile( id, filepath, fullname, title, description )

    # Add the FS File instance to self
    self._setObject(id, temp_obj)


class FSFile( ContentBase ):
    """ 
        FS File class.
        Objects of this class represent File System files
    """
    _class_version = 1.00

    __implements__ = ( ContentBase.__implements__
                     , Features.isFSFile
                     )

    meta_type = 'FS File'
    portal_type = 'FS File'

    isCategorial = 0
    isDocument = 0
    isPrincipiaFolderish = 0

    security = ClassSecurityInfo()

    _size = None
    
    def __init__( self, id, filepath, fullname, title='', description='' ):
        """
            Constructs instance of FSFile.
            
            Arguments:
                
                'id' -- Object identifier.
                
                'filepath' -- Path in FS to the object we want to wrap.
                
                'fullname' -- File name recoded to python charset.
                
                'title' -- Optional title.
                
                'description' -- Optional decription.
        """
        ContentBase.__init__( self, id, title )
        #full name we get here is already recoded
        self._fullname = fullname
        self._basename, self._extension = nt_splitext( fullname )
        
        while self._extension and self._extension[0]=='.':
            self._extension = self._extension[1:]

        self.title = title or self._basename
        self._filepath = filepath

        st = os.stat( filepath )
        self.creation_date = DateTime(st[stat.ST_MTIME])
        self.modification_date = DateTime(st[stat.ST_MTIME])

        self.get_size(reRead=1)

        #guess content type
        self.content_type, enc = guess_content_type( name=fullname.lower(), default=Config.DefaultAttachmentType )
    
    def setModificationDate( self, modification_date=None ):
        """
            Sets the date when the resource was last modified.
            When called without an argument, updates date from file in filesystem.
        """
        if modification_date is None:
            self.modification_date = DateTime( os.stat( self._filepath )[stat.ST_MTIME] )
        else:
            self.modification_date = self._datify(modification_date)

    def modified( self ):
        """
            Dublin Core element - date resource last modified, returned as DateTime
        """
        date = self.modification_date
        if date is None:
            # Upgrade.
            date = DateTime( os.stat( self._filepath )[stat.ST_MTIME] )
            self.modification_date = date
        self.checkUpdate()
        return date

    security.declareProtected( CMFCorePermissions.View, 'read' )
    def read( self ):
        """
            Returns contents of wrapped FS file.
            Used in ExternalEditor.
        """
        data = StringIO()
        self._read( data )
        return data.getvalue()
    
    security.declareProtected( CMFCorePermissions.View, '_read' )
    def _read( self, outstream ):
        """
            Reads binary data from file and writes it to outstream.

            Arguments:

                'outstream' -- Object of file type.
        """
        try:
            fp = open(self._filepath, 'rb')
            try:
                size=self.get_size(reRead=1)
                fp.seek(0)
                blocksize=2<<16
                pos=0
                while pos<size:
                    outstream.write(fp.read(blocksize))
                    pos=pos+blocksize
                fp.seek(0)
            except:
                outstream.write(fp.read())
            fp.close()
        except IOError:
            pass
        
    #XXX may be use FSImage.index_html instead ???
    security.declareProtected( CMFCorePermissions.View, 'index_html' )
    def index_html( self, REQUEST, RESPONSE ):
        """
            Returns the file data
        """
        self.checkUpdate()
        RESPONSE.setHeader('Content-Type', self.content_type)
        RESPONSE.setHeader('Content-Length', self.get_size())

        RESPONSE.setHeader( 'Content-Disposition', '%s; filename="%s"; size="%d"' % \
            ( self.content_type, self._fullname, self.get_size() ) )
        self._read(outstream=RESPONSE)

    def getOwner( self ):
        """
            Returns owner for this object.
            There is no owner for objects stored in file system.
        """
        #no owner for filesystem objects
        return None
    
    security.declareProtected( CMFCorePermissions.View, 'get_size' )
    def get_size( self, reRead=0 ):
        """
            Returns the FS file size.

            Arguments:

                'reRead' -- If true, forces to update size from FS.
        """
        if not self.checkExists():
            self._size = None
        if reRead:
            try:
                self._size = os.stat(self._filepath)[stat.ST_SIZE]
            except:
                self._size = None
        return self._size

    security.declareProtected(CMFCorePermissions.View, 'getSize')
    getSize = get_size

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'getObjectFSPath' )
    def getObjectFSPath( self ):
        """
            Returns the path of the file in FS
        """
        self.checkUpdate()
        return self._filepath

    def _getCopy( self, container ):
        """ 
            Copy operation support.

            Creates HTMLDocument, inserts FS file as attachment, pastes link to
            the attachment in document text and tries to associate document text
            with attachment.
        """
        id = cookId(container, self.id)
        container.invokeFactory( 'HTMLDocument', id , title=self.title, description=self.description)
        ob = container[id]
        
        class fake: pass
        
        item = fake()
        item.file = open(self._filepath, 'rb')
        item.filename = "%s_attach.%s" % (self._basename, self._extension)
        #item.headers  = {'Content-type': self.content_type}
        item.headers = None

        ob.addFile( file=FileUpload(item), title=self._fullname, try_to_associate=1, paste=1)
        container._delObject(id)
        item.file.close()

        return ob

    security.declareProtected( CMFCorePermissions.View, 'getFullName' )
    def getFullName( self ):
        """
            Returns full FS file name.
            The name was recoded to python charset.
        """
        return self._fullname

    security.declareProtected( CMFCorePermissions.View, 'getFilePath' )
    def getFilePath( self ):
        """
            Returns the FS file object path (recoded for view to python charset)
        """
        msg = getToolByName( self, 'msg', None )
        lang = msg.get_selected_language()
        
        sys_charset = Config.Languages.get(lang)['system_charset']
        python_charset = Config.Languages.get(lang)['python_charset']
        
        fpath = recode_string(self._filepath, enc_from=sys_charset, enc_to=python_charset)
        return fpath

    security.declareProtected( CMFCorePermissions.View, 'checkExists' )
    def checkExists( self ):
        """
            Check if file in FS exists
        """
        if os.path.exists(self._filepath):
            return 1
        return 0
        
    security.declareProtected( CMFCorePermissions.View, 'checkUpdate' )
    def checkUpdate( self, *args, **kw ):
        """
            Checks if object modification time is the same with that of os file.
            Updates size and modification time if the file in FS was modified.
        """
        if not self.checkExists():
            return
        st = os.stat(self._filepath)
        mt = DateTime(st[stat.ST_MTIME])
        if mt != self.modification_date:
            #file was changed
            self.get_size(reRead=1)
            self.modification_date = mt
            self.reindexObject()

    security.declareProtected( CMFCorePermissions.View, 'isViewable' )
    def isViewable( self ):
        """
            Checks if object can be viewed in browser
        """
        return self._extension.lower() in ['bmp','jpg','gif','png','pcx','txt','htm','html']

    security.declareProtected( CMFCorePermissions.View, 'getIcon' )
    def getIcon( self ):
        """
            Returns the file type sensitive icon
        """
        icon = factory_type_information[0]['icon']
        icon = Config.Icon2FileMap.get( self._extension.lower(), icon )
        return icon

InitializeClass( FSFile )
