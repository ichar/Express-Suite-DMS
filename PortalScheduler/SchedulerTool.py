""" 
Portal Scheduler. SchedulerTool class

*** Checked 11/10/2008 ***

"""
__version__='$Revision: 1.0 $'[11:-2]

import Globals
from Globals import InitializeClass, DTMLFile

from Acquisition import aq_inner, aq_parent
from AccessControl import ClassSecurityInfo

from Products.CMFCore.ActionProviderBase import ActionProviderBase
from Products.CMFCore.ActionInformation import ActionInformation
from Products.CMFCore.Expression import Expression
from Products.CMFCore import permissions as CMFCorePermissions

from Scheduler import Scheduler

from zLOG import INFO, ERROR
from Logger import LOG


class SchedulerTool( Scheduler, ActionProviderBase ):

    meta_type = 'Portal Scheduler Tool'

    _actions = ( ActionInformation( \
                       id='manage',
                       title='Manage scheduler',
                       action=Expression( text='string: ${portal_url}/manage_scheduler_form' ),
                       permissions=( CMFCorePermissions.ManagePortal, ),
                       category='global',
                       visible=1
                     ),
               )

    security = ClassSecurityInfo()

    manage_options = ( Scheduler.manage_options +
                       ({ 'label' : 'Overview', 'action' : 'manage_overview' }, ) +
                       ActionProviderBase.manage_options
                     )

    #
    #   ZMI methods
    #
    security.declareProtected( CMFCorePermissions.ManagePortal, 'manage_overview' )
    manage_overview = DTMLFile( 'dtml/explainSchedulerTool', globals() )

    def __init__( self ):
        Scheduler.__init__( self, id='portal_scheduler' )

    security.declarePrivate('listActions')
    def listActions( self, info=None ):
        """
            Returns available actions via tool
        """
        return self._actions
