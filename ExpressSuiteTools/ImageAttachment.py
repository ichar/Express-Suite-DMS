"""
Image attachment class.
Supports tiff images with multiple frames.

$Id: ImageAttachment.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 21/01/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re
from cStringIO import StringIO
from ntpath import basename as nt_basename, splitext as nt_splitext
try: from PIL import Image
except ImportError: pass

from AccessControl import ClassSecurityInfo
from AccessControl.SecurityManagement import getSecurityManager
from Acquisition import aq_base, aq_get, aq_inner, aq_parent
from ZPublisher.HTTPRequest import FileUpload

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.Expression import Expression
from Products.CMFCore.utils import getToolByName,  _checkPermission
from Products.Photo import Photo

import Config, Features
from ActionsTool import ActionInformation
from Features import createFeature
from SimpleObjects import ContentBase
from Utils import InitializeClass

from logging import getLogger
logger = getLogger( 'ImageAttachment' )

try:
    from webdav.Lockable import wl_isLocked
except ImportError:
    # webdav module not available
    def wl_isLocked(ob):
        return 0


class ImageAttachment( ContentBase, Photo ):
    """
        Image which supports tiff images with multiple frames
    """
    _class_version = 1.0

    meta_type = 'Image Attachment'
    portal_type = 'Image Attachment'

    security = ClassSecurityInfo()

    __implements__ = createFeature('isImageAttachment'), \
                     Features.isAttachment, \
                     Features.isImage, \
                     ContentBase.__implements__, \
                     Photo.__implements__

    # for use by external editor
    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'PUT' )

    _properties = ContentBase._properties + \
                  Photo._properties + \
                  (
                      {'id':'filename',	'type':'string'},
                  )

    _actions = ( \
                ActionInformation(
                    id='recognize',
                    title="Recognize attachment",
                    description="Recognize attachment",
                    icon='external_editor.gif',
                    action=Expression('string: ${object_url}/recognizeAttachment'),
                    permissions=( CMFCorePermissions.ModifyPortalContent, ),
                    condition=Expression("python: object.isVersionAllowedToModify()")
                ),
         ) + ContentBase._actions

    # default attribute values
    filename = None
    icon = Photo.icon
    getContentType = Photo.content_type

    def __init__( self, id, title, file, content_type='', precondition='', store='Image', \
                  engine='PIL', quality=75, pregen=0, timeout=0):
        """
            Initializes class instance
        """
        ContentBase.__init__( self, id )
        Photo.__init__(self, id, title, file, content_type, precondition,
                 store, engine, quality, pregen, timeout)
        file.seek(0)
        self._data = file.read()
        self._num_frames = 0
        self._is_TIFF = 0

        #photoconf = self.propertysheets.get('photoconf')
        #photoconf.manage_changeProperties(timeout=3600)
        #photoconf.manage_changeProperties()

        filename = isinstance( file, FileUpload ) and file.filename or id
        self._setPropValue( 'filename', nt_basename( filename ) )

        #force given content type
        #if content_type:
        #    self._setPropValue( 'content_type', content_type )

    def getBase( self ):
        return aq_parent(aq_inner(self))

    def getIcon(self, relative_to_portal=0):
        """
            Returns the portal-relative icon for this type.
            Returns Photo's icon, not dtmldoc.gif icon.
        """
        if relative_to_portal:
            return self.icon

        if not self.icon:
            icon = '/misc_/Photo/photo.gif'
        else:
            # Relative to REQUEST['BASEPATH1']
            portal_url = getToolByName( self, 'portal_url' )
            icon = portal_url(relative=1) + '/' + self.icon
            while icon[:1] == '/':
                icon = icon[1:]

        return icon

    def Extension( self ):
        """ 
            Returns extention of object
        """
        id = self.getId()
        try: extension = nt_splitext( id )[1][1:]
        except: extension = 'image'
        return extension

    def SearchableText( self ):
        """ 
            Returns indexable text for the fulltext search
        """
        id = self.getId()
        text = '%s %s %s' % ( self.Title(), id, self.Extension() )
        if hasattr(self, 'getBase'):
            base = self.getBase()
            text = '%s %s %s %s' % ( base.Title(), base.Description(), \
                hasattr(base, 'registry_numbers') and base.registry_numbers() or '', \
                text )
        return text

    security.declareProtected( CMFCorePermissions.View, 'RawBody' )
    def RawBody( self ):
        """
            Returns raw image data.

            Result:

                String (potentially big).
        """
        return str( self._original.data )

    security.declarePublic('isVersionAllowedToModify')
    def isVersionAllowedToModify(self):
        """
            Whether or not can user modify version
        """
        return _checkPermission( CMFCorePermissions.ModifyPortalContent, aq_parent(self) )

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'recognizeAttachment' )
    def recognizeAttachment( self, REQUEST ):
        """
            Opens this object in the External Editor
        """
        #XXX: move this to ExternalEditor or drop out useless lines of code
        RESPONSE = REQUEST.RESPONSE
        security = getSecurityManager()
        ob = self

        #ob - ImageAttachement.
        version = aq_parent(ob)
        document = version.getVersionable()

        #the real permission check goes here:
        if not self.isVersionAllowedToModify():
            raise Unauthorized, 'You are not allowed to modify document version.'

        r = []
        r.append('url:%s' % ob.absolute_url())
        r.append('url2:%s' % version.absolute_url() )
        #r.append('url2:%s' % document.absolute_url() )
        r.append('meta_type:%s' % ob.meta_type)
        #r.append('meta_type:%s' % version.meta_type)

        if hasattr(aq_base(ob), 'content_type'):
            if callable(ob.content_type):
                r.append('content_type:%s' % ob.content_type())
            else:
                r.append('content_type:%s' % ob.content_type)

        if hasattr(aq_base(version), 'content_type'):
            if callable(version.content_type):
                r.append('content_type2:%s' % version.content_type())
            else:
                r.append('content_type2:%s' % version.content_type)
#        r.append('content_type2:text/plain')

        r.append( 'feature:recognize' )

        if REQUEST._auth:
            if REQUEST._auth[-1] == '\n':
                auth = REQUEST._auth[:-1]
            else:
                auth = REQUEST._auth
            r.append('auth:%s' % auth)

        r.append('cookie:%s' % REQUEST.environ.get('HTTP_COOKIE',''))

        #here we check lock on version, not object itself
#        if wl_isLocked(version):
        if wl_isLocked(document):
            # Version is locked, send down the lock token
            # owned by this user (if any)
            user_id = security.getUser().getId()
#            for lock in version.wl_lockValues():
            for lock in document.wl_lockValues():
                if not lock.isValid():
                    continue # Skip invalid/expired locks
                creator = lock.getCreator()
                if creator and creator[1] == user_id:
                    # Found a lock for this user, so send it
                    r.append('lock-token:%s' % lock.getLockToken())
                    if REQUEST.get('borrow_lock'):
                        r.append('borrow_lock:1')
                    break

        r.append('')

        RESPONSE.setHeader('Pragma', 'no-cache')

        if hasattr(aq_base(ob), 'data') \
           and hasattr(ob.data, '__class__') \
           and ob.data.__class__ is Image.Pdata:
            # We have a File instance with chunked data, lets stream it
            metadata = '\n'.join(r )
            RESPONSE.setHeader('Content-Type', 'application/x-zope-edit')
            RESPONSE.setHeader('Content-Length',
                               len(metadata) + ob.get_size() + 1)
            RESPONSE.write(metadata)
            RESPONSE.write('\n')
            data = ob.data
            while data is not None:
                RESPONSE.write(data.data)
                data = data.next
            return ''
        if hasattr(ob, 'manage_FTPget'):
            try:
                r.append(ob.manage_FTPget())
            except TypeError: # some need the R/R pair!
                r.append(ob.manage_FTPget(REQUEST, RESPONSE))
        elif hasattr(ob, 'EditableBody'):
            r.append(ob.EditableBody())
        elif hasattr(ob, 'document_src'):
            r.append(ob.document_src(REQUEST, RESPONSE))
        elif hasattr(ob, 'read'):
            r.append(ob.read())
        else:
            # can't read it!
            raise 'BadRequest', 'Object does not support external editing'

        RESPONSE.setHeader('Content-Type', 'application/x-zope-edit')
        return '\n'.join(r )

    security.declareProtected( CMFCorePermissions.View, 'getFramesNumber' )
    def getFramesNumber(self):
        """
            Returns number of frames in the image.

            Result:

                int
        """
        return self._num_frames

    security.declareProtected(CMFCorePermissions.View, 'isTIFF' )
    def isTIFF(self):
        """
            Returns whether this image is in tiff format.

            Result:

                Boolean.
        """
        return self._is_TIFF

    def index_html(self, REQUEST, RESPONSE, display=None):
        """
            Returns the image data
        """
        # display may be set from a cookie (?)
        if display and self._displays.has_key(display):
            if not self._isGenerated(display):
                # Generate photo on-the-fly
                if re.match(r'frame\d', display) and not Config.SaveImageFrames and \
                    self.getFramesNumber() > 1:
                    #do not store rendered image
                    return self._getDisplayPhoto(display).index_html(REQUEST, RESPONSE)
                elif not re.match(r'thumbnail_frame\d', display) and not Config.SaveImageDisplays:
                    return self._getDisplayPhoto(display).index_html(REQUEST, RESPONSE)
                self._makeDisplayPhoto(display, 1)
            else:
                timeout = self.propertysheets.get('photoconf').getProperty('timeout')
                if timeout and self._photos[display]._age() > (timeout / 2):
                    self._expireDisplays((display,), timeout)
            # Return resized image
            return self._photos[display].index_html(REQUEST, RESPONSE)

        # Return original image
        return self._original.index_html(REQUEST, RESPONSE)

    def _shouldGenerate(self, display):
        """
            Returns whether display should be generated.
        """
        return (self._isGenerated(display) or self.propertysheets.get('photoconf').getProperty('pregen') or
               ( self.isTIFF() and re.match(r'thumbnail_frame\d+', display) ) )

    def _getDisplayData(self, display):
        """
            Returns raw photo data for given display.

            Changes Photo._getDisplayData() the next way: if self is tiff image
            and display format is "frameXX" or "thumbnail_frameXX", frame number
            XX will be converted to PNG and resized according its settings.

            Arguments:

                'display' -- name of display to use

            Result:

                file object (StringIO).
        """
        (width, height) = self._displays[display]
        if width == 0 and height == 0:
            width = self._original._width()
            height = self._original._height()

        (width, height) = self._getAspectRatioSize(width, height)
        engine = self.propertysheets.get('photoconf').getProperty('engine')
        quality = self.propertysheets.get('photoconf').getProperty('quality')
        if self._is_TIFF and ( re.match(r'frame\d+', display) or
            re.match(r'thumbnail_frame\d+', display) ):
            #generate PNG frame
            try:
                frameno = int(display.replace('frame', ''))
            except ValueError:
                frameno = int(display.replace('thumbnail_frame', ''))

            im = Image.open( StringIO(self._original._data()) )
            im.seek(0)
            try:
                for frame in range(frameno):
                    im.seek(im.tell()+1)
            except EOFError:
                pass # end of sequence

            png_data = StringIO()
            im.save(png_data, 'PNG')

            # creating Photo containing PNG data
            png_data.seek(0)
            return self._resize(display, width, height, engine, quality, frame_data=png_data)
        else:
            return self._resize(display, width, height, engine, quality)

    def _resize(self, display, width, height, engine='PIL', quality=75, frame_data=None):
        """
            Resize and resample photo.

            Arguments:

                'frame_data' -- File object (StringIO). If given, forces to use
                it as image data in place of original image data.

                'display, width, height, engine, quality' -- see Photo._resize for
                more help

            Result: resized image (file object)

            Extends Photo._resize to resize only given frame if needed.
        """
        newimg = StringIO()
        if engine == 'PIL':  # Use PIL
            if frame_data is not None:
                img = Image.open( frame_data )
            else:
                img = Image.open(self._original._PILdata())
            fmt = img.format
            img = img.resize((width, height))
            img.save(newimg, fmt, quality=quality)
        elif engine == 'ImageMagick':  # Use ImageMagick
            #do not convert multi-framed tiffs
            origimg = self._original
            if sys.platform == 'win32':
                from win32pipe import popen2
                imgin, imgout = popen2('convert -quality %s -geometry %sx%s - -'
                                       % (quality, width, height), 'b')
            else:
                from popen2 import popen2
                imgout, imgin = popen2('convert -quality %s -geometry %sx%s - -'
                                       % (quality, width, height))
            imgin.write(origimg._IMdata())
            imgin.close()
            newimg.write(imgout.read())
            imgout.close()

        newimg.seek(0)
        return newimg

    def _instance_onCreate( self ):
        """
            Handle pasting of new photos
        """
        if hasattr(self, '_original'):
            return

        # Added Photo (vs. imported)
        # See note in PUT()
        store = self.propertysheets.get('photoconf').getProperty('store')
        if store == 'Image':
            from Products.Photo.PhotoImage import PhotoImage
        elif store == 'ExtImage':
            from Products.Photo.ExtPhotoImage import PhotoImage
        try:
            self._original = PhotoImage(self.id, self.title, path=self.absolute_url(1))
            self._original.manage_upload( StringIO(self._data), self.content_type() )
        except:
            logger.error('_instance_onCreate image upload id %s, path %s' % ( self.id, self.absolute_url() ), exc_info=True)
            self._original = None
            return

        #content_type = self.propertysheets.get('photoconf').getProperty('content_type')
        #if content_type:
        #    self._original.content_type = content_type
        if hasattr(self, '_data'):
            im = Image.open( StringIO(self._data) )
            try:
                im.seek(0)
            except ValueError:
                #this is gif or something else (one frame only)
                pass
            self._num_frames = 0
            displays = self._displays
            self._original.width, self._original.height = im.size
            try:
                while 1:
                    #displays["frame%d" % self._num_frames]=im.size
                    displays["frame%d" % self._num_frames]=(944, 944) #resize to fit in page
                    displays["thumbnail_frame%d" % self._num_frames]=(128, 128) #thumbnails for frame
                    im.seek(im.tell()+1)
                    self._num_frames += 1
            except EOFError:
                pass # end of sequence
            self._displays = displays
            self._num_frames += 1

            delattr(self, '_data')
        if self._validImage():
            self._makeDisplayPhotos()

    def _instance_onClone( self, source, item ):
        """
            Prepare photos for cloning
        """
        Photo.manage_afterClone( self, item )

    def _containment_onAdd( self, item, container ):
        self._original.manage_afterAdd( item, container )
        if hasattr( self, '_photos' ):
            for photo in self._photos.values():
                photo.manage_afterAdd( item, container )

    def _containment_onDelete( self, item, container ):
        Photo.manage_beforeDelete( self, item, container )

InitializeClass( ImageAttachment )
