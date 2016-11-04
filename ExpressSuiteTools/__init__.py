"""
Init of application package
$Id: __init__.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 30/05/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import Globals

import sys, os, os.path
from types import StringType, TupleType
from email.Charset import BASE64, QP, ALIASES, CHARSETS, add_charset, add_alias, add_codec

# apply patches before initialization of our classes
import Patches
import XBroken

from AccessControl.Permission import registerPermissions
from App.Common import package_home
from ZClasses import createZClassForBase

from Products.CMFCore import utils as CMFCoreUtils
from Products.CMFCore.DirectoryView import registerDirectory
from Products.ZMySQLDA import DA

from Products.PortalScheduler import SchedulerTool
import Config

this_module = sys.modules[ __name__ ]

# add 'bin' subdirectory to the system search path
bin_dir = os.path.join( package_home( globals() ), 'bin' )
path_list = os.environ.get( 'PATH', '' ).split( os.pathsep )

if os.access( bin_dir, os.X_OK ) and bin_dir not in path_list:
    path_list.insert( 0, bin_dir )
    os.environ['PATH'] = os.pathsep.join( path_list )

del bin_dir, path_list

# check whether the Python Imaging Library is installed
if not hasattr( Config, 'UsePILImage' ):
    try: import PIL.Image
    except ImportError: Config.UsePILImage = 0
    else: Config.UsePILImage = 1

# register our DTML tags
import DTMLTags

# load core
import ExpressSuiteCore

# load CatalogTool
if Config.IsSQLCatalog:
    import ISAMSupporter
    import ZSQLCatalogTool as CatalogTool
    import ZSQLFollowupActionsTool as FollowupActionsTool
else:
    import CatalogTool
    import FollowupActionsTool

# load Application modules
import ActionsTool
import BackupFSRoot
import CommentsTool
import DiscussionItem
import DocumentLinkTool
import ErrorLogTool
import File
import ForestTag
import HelpTool
import HTMLCleanup
import JungleTag
import Mail
import ManageCMFContent
import MemberDataTool
import MembershipTool
import MetadataTool
import PropertiesTool
import SecureImports
import ServicesTool
import SimpleAppItem
import TypesTool
import UserFolder
import WorkflowTool

#import MigrationTool

__module_aliases__ = ( \
    ( 'Products.CommonTools', 'Products.ExpressSuiteTools' ),
)

# build transliteration maps
for lang, tables in Config.TransliterationMap.items():
    charmap = {}
    tables = [ tables ]

    while tables:
        table = tables.pop(0)
        if type(table) is TupleType:
            tables[ 0:0 ] = list( table )
            continue
        elif type(table) is StringType:
            tables.insert( 0, Config.TransliterationMap[ table ] )
            continue

        table.setdefault( ' ', '_' )

        for i in range(256):
            c = chr(i)
            if table.has_key(c):
                charmap[c] = table[c]
            elif not charmap.has_key(c):
                charmap[c] = c

    Config.TransliterationMap[ (lang,) ] = charmap

# fix Russian charsets in email package
_charset_map = {
        'cp1251' : ( QP, None, None ),
        'koi8-r' : ( QP, None, None ),
    }

_charset_aliases = { 'windows-1251' : 'cp1251', }

for name, item in _charset_map.items():
    add_charset( name, *item )
    add_codec( name, name )

for alias, name in _charset_aliases.items():
    add_alias( alias, name )

# register custom permissions
perms = filter( lambda p: p[0] != '_', dir( Config.Permissions ) )
perms = map( lambda p: ( getattr( Config.Permissions, p ), () ), perms )
registerPermissions( perms, () )
del perms

ADD_CONTENT_PERMISSION = 'Add portal content'

bases = ( HTMLDocument.HTMLDocument, HTMLCard.HTMLCard, )
tools = ( \
          ActionsTool.ActionsTool
        , CatalogTool.CatalogTool
        , CommentsTool.CommentsTool
        , DocumentLinkTool.DocumentLinkTool
        , ErrorLogTool.ErrorLogTool
        , FollowupActionsTool.FollowupActionsTool
        , HelpTool.HelpTool
        , MemberDataTool.MemberDataTool
        , MembershipTool.MembershipTool
        , MetadataTool.MetadataTool
        , PropertiesTool.PropertiesTool
        , ServicesTool.ServicesTool
        , SchedulerTool.SchedulerTool
        , TypesTool.TypesTool
        , WorkflowTool.WorkflowTool
       #, MigrationTool.MigrationTool
        )

# Deriving appboardItems from ZClass
for base in bases:
    createZClassForBase( base, this_module )

# Make skins available as DirectoryViews
registerDirectory('skins', globals())
for x in Config.SkinViews:
    registerDirectory('skins/%s' % x, globals())

# Make user manual available through web
registerDirectory('manual', globals())

# make external editors available through web
registerDirectory('zopeeditor', globals())

z_bases = CMFCoreUtils.initializeBasesPhase1( bases, this_module )
z_tool_bases = CMFCoreUtils.initializeBasesPhase1( tools, this_module )


def initialize( context ):

    product = context._ProductContext__prod

    Config.ProductName = product.id
    Config.ProductVersion = product.version.split()[-1]

    Config.ZopeInfo = context._ProductContext__app.Control_Panel.version_txt()
    Config.PythonInfo = sys.version.replace('\r','').replace('\n',' ')
    Config.SystemInfo = '%s (%s)' % ( sys.platform, os.name )

    Config.MaintainanceMode = {}

    context.registerClass( ExpressSuiteCore.ExpressSuiteCore,
          constructors = ( ExpressSuiteCore.manage_addExpressSuiteForm,
                           ExpressSuiteCore.manage_addExpressSuite ),
          icon = 'icons/portal_instance.gif'
        )

    context.registerClass( UserFolder.UserFolder,
          permission = 'Add User Folders',
          constructors = ( UserFolder.addUserFolder, ),
        )

    #context.registerClass( DA.Connection,
    #      constructors = ( ExpressSuiteCore.addZMySQLConnection, ),
    #    )

    for module in [ File, Mail, BackupFSRoot ]:
        module.initialize( context )

    Config.AttachmentSearchable = None

    CMFCoreUtils.initializeBasesPhase2( z_tool_bases, context )

    CMFCoreUtils.ToolInit( 'DMS Express Suite Tools', tools=tools, product_name='ExpressSuiteTools', icon='tool.gif', \
                          ).initialize( context )

    CMFCoreUtils.ContentInit( 'DMS Express Suite Content'
                             , content_types=( \
                                      DiscussionItem.DiscussionItem
                                    , DTMLDocument.DTMLDocument
                                    , FSFile.FSFile
                                    , FSFolder.FSFolder
                                    , Heading.Heading
                                    , HTMLDocument.HTMLDocument
                                    , HTMLCard.HTMLCard
                                    , MailFolder.IncomingMailFolder
                                    , MailFolder.OutgoingMailFolder
                                    , MailFolder.FaxIncomingFolder
                                    , Registry.Registry
                                    , SearchProfile.SearchProfile
                                    , Shortcut.Shortcut
                                    )
                     , permission = ADD_CONTENT_PERMISSION
                     , extra_constructors=( \
                                      DiscussionItem.addDiscussionItem
                                    , DTMLDocument.addDTMLDocument
                                    , FSFile.addFSFile
                                    , FSFolder.addFSFolder
                                    , Heading.addHeading
                                    , HTMLDocument.addHTMLDocument
                                    , HTMLCard.addHTMLCard
                                    , MailFolder.addIncomingMailFolder
                                    , MailFolder.addOutgoingMailFolder
                                    , MailFolder.addFaxIncomingFolder
                                    , Registry.addRegistry
                                    , SearchProfile.addSearchProfile
                                    , Shortcut.addShortcut
                                    )
                     , fti=ExpressSuiteCore.factory_type_information
                     ).initialize( context )

    context.registerHelpTitle( 'ExpressSuite Help' )
    context.registerHelp( directory='help' )
