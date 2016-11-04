"""
Docflow role manager class.
$Id: DFRoleManager.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 16/01/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from zLOG import LOG, ERROR, TRACE

from Products.CMFCore.utils import getToolByName

from Config import EditorRole
from DepartmentDictionary import departmentDictionary


class DFRoleManager:
    """
        Docflow roles manager
    """
    def __init__( self ):
        pass

    def getUserIdByRole( self, parent, object, role_id, segment_uid, dept_title=None ):
        """
            Returns user id by role.

            Arguments:

                'parent' -- object for calling 'getToolByName'

                'object' -- object according which roles will be analized

                'role_id' -- id of role

            Result:

                Returns array of user's id matching to specified role.
        """
        user_ids = []
        membership = getToolByName( parent, 'portal_membership' )
        member = membership.getAuthenticatedMember()
        msg = getToolByName( parent, 'msg' )

        if role_id == '__role_VersionOwner':
            user_ids = [ object.getVersion().getOwner() ]
        elif role_id == '__role_Owner':
            if object.implements( 'isVersion' ):
                user_ids = [ object.aq_parent.getOwner() ]
            else:
                user_ids = [ object.getOwner() ]

        elif role_id == '__role_Group_Department':
            if dept_title:
                group_id = membership.getGroupIdByTitle( dept_title )
                if not group_id:
                    raise ValueError, msg('User group is not reachable')
                user_ids = membership.getGroupMembers( group_id )
            else:
                raise ValueError, msg('Department folder is not defined')

        elif role_id == '__role_Chief_Department':
            access_name = EditorRole
            if dept_title:
                #get the folder with given title
                department_folder = departmentDictionary.getSubFolderByTitle( parent, segment_uid, dept_title )
                if not department_folder:
                    raise ValueError, '%s $ chief of department: %s $ error' % ( 'Department folder is not reachable', dept_title )
                user_ids = self.getUserListWithGivenAccess( parent, department_folder, access_name, inherited=0 )
            else:
                raise ValueError, '%s $ none title of department: %s:%s $ error' % ( 'Department folder is not reachable', member, dept_title )

        elif role_id == '__role_WorkflowChief_Department':
            access_name = 'WorkflowChief'
            if dept_title:
                #get the folder with given title
                department_folder = departmentDictionary.getSubFolderByTitle( parent, segment_uid, dept_title )
                if not department_folder:
                    raise ValueError, '%s $ workflow chief of department: %s $ error' % ( 'Department folder is not reachable', dept_title )
                user_ids = self.getUserListWithGivenAccess( parent, department_folder, access_name, inherited=0 )
            elif member is not None:
                #first test current user's home folder
                home_folder = member.getHomeFolder()
                user_ids = self.getUserListWithGivenAccess( parent, home_folder, access_name, inherited=0 )
                if not user_ids:
                    #if did not found users with WorkflowChief role
                    #search folder based on segment and users departmnet
                    title = member.getMemberDepartment()
                    if not title:
                        raise ValueError, '%s $ home: %s $ error' % ( 'Department is not set in users settings', home_folder )
                    #get the folder with given title
                    department_folder = departmentDictionary.getSubFolderByTitle( parent, segment_uid, title )
                    if department_folder is None:
                        raise ValueError, '%s $ member: %s:%s $ error' % ( 'Department folder is not reachable', member, title )
                    user_ids = self.getUserListWithGivenAccess( parent, department_folder, access_name, inherited=1 )
        
        elif role_id in ['__role_Reader', '__role_Writer', '__role_Editor', '__role_WorkflowChief']:
            access_name = role_id[len('__role_'):]
            user_ids = self.getUserListWithGivenAccess( parent, object, access_name, inherited=1 )

        if not user_ids:
            LOG('DFRoleManager.getUserIdByRole', ERROR, "user_ids is empty, role: %s, department: '%s'" % ( role_id, dept_title ))

        return [ str(id) for id in user_ids if id is not None ]

    def getUserListWithGivenAccess( self, parent, object, access_name, inherited=None ):
        """
            Returns user ids list by role.

            Arguments:

                'object' -- object according which roles will be analized

                'access_name' -- id of role

                'inherited' -- flag to alalize inherited roles

            Result:

                Returns array of user's id matching to specified role.
        """
        user_ids = []
        # membership = getToolByName( parent, 'portal_membership' )
        # users_ids = portal_membership.listAllowedUsers( object, access_name )
        roles = object.getLocalRoles()
        if roles:
            for id, role in roles:
                if not inherited and '__inherited' in role:
                    continue
                elif access_name in role:
                    user_ids.append( id )

        return user_ids
