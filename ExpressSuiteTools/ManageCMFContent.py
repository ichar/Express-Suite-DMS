"""
Manage CMF site content
$Id: ManageCMFContent.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 04/03/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re, sys, os.path
from cStringIO import StringIO
from string import split, rfind, strip, join

from App.Common import package_home
from Globals import DTMLFile

from Products.CMFCore import DirectoryView
from Products.CMFCore.utils import minimalpath, getToolByName
from Products.CMFCore.SkinsContainer import SkinsContainer


class ManageCMFContent:
    """
        A suite of methods deploying CMF site
    """
    def __init__( self, stream=None ):
        """
            Stream is expected to be some writable file object, like a StringIO, that output will be sent to
        """
        if stream is not None:
            self.stream = stream
        else:
            self.stream = StringIO()

    def deploy_class( self, target, type_name, fti ):
        """
            Register a new type
        """
        write = self.stream.write
        tptypes = getToolByName( target, 'portal_types', None )

        if tptypes is None:
            write( 'No portal_skins' )
        elif not tptypes.getTypeInfo( type_name ):
            tptypes.addType( type_name, fti[0] )
            write( 'Added type object for %s \n' % type_name )
        else:
            write( 'Skipping type object for %s (already exists) \n' % type_name )

    def register_view( self, target, view ):
        """
            Register a directory view
        """
        skins = getToolByName( target, 'portal_skins', None )
        write = self.stream.write

        if skins._getOb( view, None ) is not None:
            write( "Failed to register view '%s' (already exists)\n" % view )
            return view

        found = 0
        dw_path = os.path.join( minimalpath(package_home( globals() )), *view.split('/') )
        dw_path = re.sub(r'\\', r'/', dw_path)

        for dir_path in DirectoryView.manage_listAvailableDirectories():
            if dir_path.endswith( dw_path ):
                found = 1
                break

        if not found:
            write( "Failed to register view '%s' (directory not found)\n" % view )
            return view

        # TODO: handle paths better
        dw_path = dw_path.replace( '\\', '/' )
        DirectoryView.manage_addDirectoryView( skins, dw_path )
        write( "Registered view '%s' = '%s'\n" % ( view, dw_path ) )

        return view

    def set_skin( self, target, views, skin_name='Site', skin_path='custom, topic, content, generic, control, Images' ):
        """
            Create a new skin
        """
        self.skin_name = skin_name
        self.skin_path = skin_path

        skins = getToolByName( target, 'portal_skins', None )
        if skins is None:
            return

        skin_paths = skins.getSkinPaths()

        include = ()
        found = 0
        for id, path in skin_paths:
           if id == self.skin_name:
              paths = path.split(', ')
              include = filter( lambda x, cp=paths: x not in cp, views ) + paths
              found = 1

        if not found:
           default_path = self.skin_path.split(', ')
           include = views + default_path

        skins.manage_properties( add_skin=1, skinname=self.skin_name, skinpath=join(include, ', ') )
        skins.default_skin = self.skin_name
