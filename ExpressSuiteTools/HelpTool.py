"""
HelpTool class
$Id: HelpTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 10/12/2007 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import Globals
from Globals import InitializeClass, DTMLFile
from AccessControl import ClassSecurityInfo

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.ActionInformation import ActionInformation
from Products.CMFCore.ActionProviderBase import ActionProviderBase
from Products.CMFCore.Expression import Expression
from Products.CMFCore.utils import UniqueObject

from OFS.SimpleItem import SimpleItem


class HelpTool( UniqueObject, SimpleItem, ActionProviderBase ):

    id = 'portal_help'
    meta_type = 'ExpressSuite Help Tool'

    _actions = ( ActionInformation( \
                              id='about'
                            , title='About Express Suite DMS'
                            , action=Expression(text='string: ${portal_url}/about')
                            , permissions=( CMFCorePermissions.View, )
                            , category='help'
                            , condition=None
                            , visible=1
                            ),
                ActionInformation(id='about'
                            , title='User manual'
                            , action=Expression(text='string: ${portal_url}/manual')
                            , permissions=(CMFCorePermissions.View,)
                            , category='help'
                            , condition=None
                            , visible=1
                            ),
                ActionInformation(id='zopeeditor'
                            , title='Setup External editor'
                            , action=Expression(text='string: ${portal_url}/zopeeditor')
                            , permissions=(CMFCorePermissions.View,)
                            , category='help'
                            , condition=None
                            , visible=1
                            )
                 )

    security = ClassSecurityInfo()

    security.declarePrivate('listActions')
    def listActions(self, info=None):
        """
          Return actions provided by tool.
        """
        return self._actions


InitializeClass( HelpTool )
