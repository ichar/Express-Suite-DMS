"""
Default document category/workflow definitions
$Id: DefaultCategories.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 30/05/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from AccessControl import Permissions as ZopePermissions

from Products.CMFCore import permissions as CMFCorePermissions
from Products.DCWorkflow.Expression import Expression

import Config, Mail
from Config import Permissions
from SimpleObjects import ExpressionWrapper

p_access        = CMFCorePermissions.AccessContentsInformation
p_list          = CMFCorePermissions.ListFolderContents
p_modify        = CMFCorePermissions.ModifyPortalContent
p_view          = CMFCorePermissions.View
p_manage        = CMFCorePermissions.ManagePortal
p_properties    = CMFCorePermissions.ManageProperties
p_addcontent    = CMFCorePermissions.AddPortalContent
p_addfolders    = CMFCorePermissions.AddPortalFolders
p_changeperms   = CMFCorePermissions.ChangePermissions
p_request       = CMFCorePermissions.RequestReview
p_reply         = CMFCorePermissions.ReplyToItem

p_delete        = ZopePermissions.delete_objects
p_ownership     = ZopePermissions.take_ownership

p_employ        = Permissions.EmployPortalContent
p_publish       = Permissions.PublishPortalContent
p_archive       = Permissions.ArchivePortalContent

p_mailhost      = Permissions.UseMailHostServices
p_mailserv      = Permissions.UseMailServerServices

p_lock          = Permissions.WebDAVLockItems
p_unlock        = Permissions.WebDAVUnlockItems

p_versions      = Permissions.CreateObjectVersions
p_makeprincipal = Permissions.MakeVersionPrincipal

r_member        = Config.MemberRole
r_manager       = Config.ManagerRole
r_visitor       = Config.VisitorRole

r_owner         = Config.OwnerRole
r_editor        = Config.EditorRole
r_reader        = Config.ReaderRole
r_writer        = Config.WriterRole
r_author        = Config.AuthorRole
r_version_owner = Config.VersionOwnerRole


def setupCategory( default_categories, id, metadata, **kw ):
    """
        Setup category
    """
    m = getattr(default_categories, 'setup%sCategory' % id, None)
    if m is None or not callable(m):
        return None
    return apply(m, ( metadata, ), kw)

def setupWorkflow( default_categories, workflow, id, metadata, **kw ):
    """
        Setup workflow definition
    """
    m = getattr(default_categories, 'setup%sWorkflow' % id, None)
    if m is None or not callable(m):
        return None
    return apply(m, ( workflow, id, metadata ), kw)


class DefaultCategories:
    #
    # Setup Document category
    #
    def setupDocumentCategory( self, metadata, **kw ):

        id = 'Document'
        prefix = '%s' % id
        category = metadata.addCategory( id, '%s' % prefix, default_workflow=0, \
                        allowed_types=['HTMLDocument', 'HTMLCard', 'DTMLDocument'] )
        if category is None:
            return None

        return category

    def setupDocumentWorkflow( self, workflow, category, metadata, **kw ):

        workflow.setProperties( title='ExpressSuite document workflow' )

        for s in ('private', 'evolutive', 'group', 'fixed', 'archive'):
            workflow.states.addState(s)

        for t in ('retract', 'evolve', 'open_for_group', 'fix', 'archive', 'activate', 'modify'):
            workflow.transitions.addTransition(t)
        #for s in ('fix', 'activate', 'allow_version_edit'):
        #   workflow.scripts._setOb( s, ExpressionWrapper( factory=Expression, use_dict=1 ) )

        for p in Config.ManagedPermissions:
            workflow.addManagedPermission(p)

        ### setup variables ###

        setupWorkflowVars(workflow)

        # Setup states
        workflow.states.setInitialState('evolutive')

        sdef = workflow.states['private']
        sdef.setProperties(
            title='Private',
            transitions=('evolve', 'fix', 'open_for_group', 'archive'))
        sdef.setPermission(p_access, 0, (r_manager, r_owner))
        sdef.setPermission(p_delete, 0, (r_manager, r_owner, r_editor))
        sdef.setPermission(p_list, 1, ())
        sdef.setPermission(p_modify, 0, (r_manager, r_version_owner))
        sdef.setPermission(p_view, 0, (r_manager, r_owner))
        sdef.setPermission(p_versions, 0, (r_manager, r_owner))
        sdef.setPermission(p_makeprincipal, 1, () )

        sdef = workflow.states['evolutive']
        sdef.setProperties(
            title='Evolutive',
            transitions=('evolve', 'retract', 'fix', 'open_for_group', 'archive', 'activate'))
        sdef.setPermission(p_view, 0, (r_manager, r_owner, r_editor, r_reader, r_writer))
        sdef.setPermission(p_versions, 0, (r_manager, r_owner, r_editor, r_writer))
        sdef.setPermission(p_delete, 0, (r_manager, r_owner, r_editor))
        sdef.setPermission(p_makeprincipal, 1, () )
        sdef.setPermission(p_modify, 0, (r_manager, r_version_owner))

        sdef = workflow.states['group']
        sdef.setProperties(
            title='Open for group',
            transitions=('retract', 'evolve', 'fix', 'archive', 'modify'))
        sdef.setPermission(p_modify, 0, (r_manager, r_owner))
        sdef.setPermission(p_lock, 1, (r_writer,))
        sdef.setPermission(p_unlock, 1, (r_writer,))
        sdef.setPermission(p_view, 0, (r_manager, r_owner, r_editor, r_reader, r_writer))
        sdef.setPermission(p_versions, 0, (r_manager, r_owner, r_editor, r_writer))
        sdef.setPermission(p_delete, 0, (r_manager, r_owner, r_editor))
        sdef.setPermission(p_makeprincipal, 1, (r_writer, r_editor))

        sdef = workflow.states['fixed']
        sdef.setProperties(
            title='Fixed',
            transitions=())
        sdef.setPermission(p_delete, 0, (r_manager,))
        sdef.setPermission(p_modify, 0, ())
        sdef.setPermission(p_view, 0, (r_manager, r_owner, r_editor, r_reader, r_writer))
        sdef.setPermission(p_versions, 0, ())
        sdef.setPermission(p_makeprincipal, 0, () )

        sdef = workflow.states['archive']
        sdef.setProperties(
            title='Archive',
            transitions=('retract', 'evolve', 'fix', 'open_for_group'))
        sdef.setPermission(p_delete, 0, (r_manager, r_editor))
        sdef.setPermission(p_modify, 0, ())
        sdef.setPermission(p_reply, 0, ())
        sdef.setPermission(p_ownership, 0, ())
        sdef.setPermission(p_properties, 0, ())
        sdef.setPermission(p_view, 0, (r_manager, r_owner, r_editor, r_reader, r_writer))
        sdef.setPermission(p_versions, 0, (r_manager, r_owner))
        sdef.setPermission(p_makeprincipal, 0, () )

        # Set transactions
        tdef = workflow.transitions['retract']
        tdef.setProperties(
            title='Hide document',
            new_state_id='private',
            actbox_name='Retract',
            actbox_url='%(content_url)s/change_state?transition=' + tdef.getId(),
            props={
                   'guard_roles': r_owner,
                  }
           )

        tdef = workflow.transitions['evolve']
        tdef.setProperties(
            title='Evolve document',
            new_state_id='evolutive',
            actbox_name='Evolve',
            actbox_url='%(content_url)s/change_state?transition=' + tdef.getId(),
            props={
                   'guard_roles' : r_owner,
                  }
           )

        tdef = workflow.transitions['open_for_group']
        tdef.setProperties(
            title='Open the document for group editing',
            new_state_id='group',
            actbox_name='Open for group',
            actbox_url='%(content_url)s/change_state?transition=' + tdef.getId(),
            props={
                   'guard_roles': r_owner,
                  }
           )

        tdef = workflow.transitions['fix']
        tdef.setProperties(
            title='Fix the document',
            new_state_id='fixed',
            actbox_name='Fix',
            actbox_url='%(content_url)s/change_state?transition=' + tdef.getId(),
            props={
                   'guard_roles': r_owner,
                  }
           )

        tdef = workflow.transitions['archive']
        tdef.setProperties(
            title='Archive document',
            new_state_id='archive',
            actbox_name='Archive',
            actbox_url='%(content_url)s/change_state?transition=' + tdef.getId(),
            props={'guard_permissions':p_archive,
                  }
           )

        tdef = workflow.transitions['activate']
        tdef.setProperties(
            title='Make current version principal',
            new_state_id='',
            actbox_name='Make the version principal',
            actbox_url='%(content_url)s/change_state?transition=' + tdef.getId(),
            props={'guard_permissions': p_makeprincipal,
                   'guard_expr':"python: (here.implements('isVersionable') or here.implements('isVersion')) and not here.isCurrentVersionPrincipal()"
                  }
            )

        tdef.addVariable( 'principal_version', "python: (here.implements('isVersionable') or here.implements('isVersion')) and here.getPrincipalVersionId()" )

        # TRIGGER_WORKFLOW_METHOD (on 'edit')
        tdef = workflow.transitions['modify']
        tdef.setProperties(
            title='Modify',
            new_state_id='',
            actbox_name='Modify',
            actbox_url='%(content_url)s/change_state?transition=' + tdef.getId(),
            trigger_type=2 # TRIGGER_WORKFLOW_METHOD
            )

        # action template make version principal
        assignActionTemplateToTransition(
            metadata=metadata,
            category_id=category,
            action_template_id=createActionTemplate_MakeVersionPrincipal( metadata, category ),
            transition='activate'
        )

        # to state 'group', set that only one version can exists in this state
        # and exclude old version by 'evolve' transition
        metadata.getCategoryById( category ).manageAllowSingleStateForVersionArray( action='add', state='group', transition_for_exclude='evolve' )

        """
        sdef = workflow.scripts['fix']
        sdef.setExpression( "python: object.implements('isVersionable') and object.denyVersionEdit()" )

        sdef = workflow.scripts['activate']
        sdef.setExpression( "python: object.implements('isVersionable') and object.activateCurrentVersion()" )

        sdef = workflow.scripts['allow_version_edit']
        sdef.setExpression( "python: object.implements('isVersionable') and object.allowVersionEdit()" )
        """

    #
    # Setup SimpleDocs category
    #
    def setupSimpleDocsCategory( self, metadata ):

        id = 'SimpleDocs'
        prefix = 'category.%s' % id
        category = metadata.addCategory( id, '%s.title' % prefix, default_workflow=0, \
                        allowed_types=[] )
        if category is None:
            return None

        args = ( prefix, 'metadata' )
        category.addAttributeDefinition( 'DocDate', 'date', '%s.%s.DocDate' % args, None )
        category.addAttributeDefinition( 'RegNo', 'string', '%s.%s.RegNo' % args, '' )

        return category

    def setupSimpleDocsWorkflow( self, workflow, category, metadata, **kw ):

        for p in Config.ManagedPermissions:
            try:
                workflow.addManagedPermission(p)
            except:
                pass

        setupWorkflowVars( workflow )

## Defaulf heading workflow ##

def setupHeadingWorkflow( workflow ):
    """
        Setup the default headings workflow
    """
    workflow.setProperties( title='ExpressSuite heading workflow' )

    for s in ('editable', 'frozen', 'fixed'):
        workflow.states.addState(s)

    for t in ('edit', 'freeze', 'fix'):
        workflow.transitions.addTransition(t)

    for p in (p_addcontent, p_addfolders, p_changeperms, p_delete, p_modify):
        workflow.addManagedPermission(p)

    # Setup states
    workflow.states.setInitialState('editable')

    sdef = workflow.states['editable']
    sdef.setProperties( 
        title='Editable',
        transitions=('fix', 'freeze'))
    sdef.setPermission(p_addcontent, 1, ())
    sdef.setPermission(p_addfolders, 1, ())
    sdef.setPermission(p_changeperms, 1, ())
    sdef.setPermission(p_delete, 1, ())
    sdef.setPermission(p_modify, 1, ())

    sdef = workflow.states['frozen']
    sdef.setProperties(
        title='Frozen',
        transitions=('edit', 'fix'))
    sdef.setPermission(p_addcontent, 0, ())
    sdef.setPermission(p_addfolders, 0, ())
    sdef.setPermission(p_changeperms, 1, ())
    sdef.setPermission(p_delete, 0, ())
    sdef.setPermission(p_modify, 0, ())

    sdef = workflow.states['fixed']
    sdef.setProperties(
        title='Fixed',
        transitions=('edit',))
    sdef.setPermission(p_addcontent, 0, ())
    sdef.setPermission(p_addfolders, 0, ())
    sdef.setPermission(p_changeperms, 0, (r_manager,))
    sdef.setPermission(p_delete, 0, ())
    sdef.setPermission(p_modify, 0, ())

    # Set transactions
    tdef = workflow.transitions['edit']
    tdef.setProperties(
        title='Edit folder',
        new_state_id='editable',
        actbox_name='Edit',
        actbox_url='%(content_url)s/heading_edit_form',
        props={ 'guard_permissions':p_changeperms }
       )

    tdef = workflow.transitions['freeze']
    tdef.setProperties(
        title='Freeze folder',
        new_state_id='frozen',
        actbox_name='Freeze',
        actbox_url='%(content_url)s/heading_freeze_form',
        props={ 'guard_permissions':p_changeperms }
       )

    tdef = workflow.transitions['fix']
    tdef.setProperties(
        title='Fix folder',
        new_state_id='fixed',
        actbox_name='Fix',
        actbox_url='%(content_url)s/heading_fix_form',
        props={ 'guard_permissions':p_changeperms }
       )

    setupWorkflowVars(workflow)

def setupWorkflowVars( workflow ):
    """
       Setup default workflow variables
    """
    for v in ('action', 'actor', 'comments', 'review_history', 'time', 'principal_version'):
        workflow.variables.addVariable(v)

    workflow.variables.setStateVar('state')

    vdef = workflow.variables['action']
    vdef.setProperties(description='The last transition',
                       default_expr='transition/getId|nothing',
                       for_status=1, update_always=1)

    vdef = workflow.variables['actor']
    vdef.setProperties(description='The ID of the user who performed '
                       'the last transition',
                       default_expr='user/getUserName',
                       for_status=1, update_always=1)

    vdef = workflow.variables['comments']
    vdef.setProperties(description='Comments about the last transition',
                       default_expr="python:state_change.kwargs.get('comment', '')",
                       for_status=1, update_always=1)

    vdef = workflow.variables['review_history']
    vdef.setProperties(description='Provides access to workflow history',
                       default_expr="state_change/getHistory",
                       props={'guard_permissions':p_view})

    vdef = workflow.variables['time']
    vdef.setProperties(description='Time of the last transition',
                       default_expr="state_change/getDateTime",
                       for_status=1, update_always=1)

    vdef = workflow.variables['principal_version']
    vdef.setProperties( description='Id of the principal version', for_status=1, \
            for_catalog=1, update_always=0, default_value='version_0.1' )

def createActionTemplate_MakeVersionPrincipal( metadata, category_id ):
    metadata.taskTemplateContainerAdapter.makeTaskDefinitionActionByRequest(
      category_id=category_id,
      action='add_root_task_definition',
      request={ "task_definition_type": "activate_version", "template_id": "_make_version_principal", "name": "Make the version principal" }
    )
    return '_make_version_principal'

def createActionTemplate_SetCategoryAttribute( metadata, category_id, task_template_id, task_template_name, attribute_name, attribute_value ):
    metadata.taskTemplateContainerAdapter.makeTaskDefinitionActionByRequest(
      category_id=category_id,
      action='add_root_task_definition',
      request={
          'task_definition_type': 'set_category_attribute',
          'template_id': task_template_id,
          'name': task_template_name,
          'attribute_name': attribute_name,
          'attribute_value': attribute_value
      }
    )
    return task_template_id

def assignActionTemplateToTransition( metadata, category_id, action_template_id, transition ):
    if not metadata.getCategoryById( category_id ).transition2TaskTemplate.has_key( transition ):
        metadata.getCategoryById( category_id ).transition2TaskTemplate[transition] = [ action_template_id ]
    else:
        metadata.getCategoryById( category_id ).transition2TaskTemplate[transition].append( action_template_id )
    metadata.getCategoryById( category_id )._p_changed = 1
