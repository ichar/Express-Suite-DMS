## Script (Python) "register"
##bind container=container
##bind context=context
##bind namespace=_
##bind script=script
##bind subpath=traverse_subpath
##parameters=password='password', confirm='confirm', domains=None, groups=[], refresh=None
##title=Register a user
##
REQUEST = context.REQUEST

if REQUEST.get('refresh', None) or refresh:
    REQUEST.set('user_email', REQUEST.get('email', ''))
    return context.join_form( context, REQUEST=REQUEST )

portal = context.portal_url.getPortalObject()
portal_properties = context.portal_properties
portal_registration = context.portal_registration
portal_membership = context.portal_membership

user = portal_membership.getAuthenticatedMember()
if user is not None and user.has_role('Manager'):
    registered_by_user = user.getUserName()
else:
    registered_by_user = None

if not REQUEST.get('noHome'):
    try:
        username = REQUEST['username']
        portal.storage.members[username]
    except KeyError:
        pass
    else:
        return context.join_form( context, REQUEST, error='Личная папка пользователя уже существует' )

if not REQUEST.get('email', ''):
    return context.join_form( context, REQUEST, error='Не указан e-mail адрес пользователя' )

#if password:
#    failMessage = portal_registration.testPasswordValidity(password, confirm)
#    if failMessage:
#        REQUEST.set( 'error', failMessage )
#        return context.join_form( context, REQUEST, error=failMessage )

failMessage = portal_registration.testPropertiesValidity(REQUEST)
if failMessage:
    REQUEST.set( 'error', failMessage )
    return context.join_form( context, REQUEST, error=failMessage )

username = REQUEST['username']
password = REQUEST.get('password') or portal_registration.generatePassword()

roles = [ 'Member', ]
if REQUEST.get('asManager'):
    roles.append( 'Manager' )

domains = domains or None
member = portal_registration.addMember( username, password, roles, domains, properties=REQUEST )
#portal_membership.setDefaultFilters(REQUEST['username'])

for group in groups:
    group_users = list( portal_membership.getGroup(group).getUsers() )
    group_users.append( username )
    portal_membership.manage_changeGroup( group, group_users )

#if portal_properties.validate_email or REQUEST.get('mail_me') or not REQUEST.get('password'):
#    try: portal_registration.registeredNotify(REQUEST['username'])
#    except: REQUEST.set('not_sended','1')

if not REQUEST.get('noHome'):
    username = member.getUserName()
    home = member.getHomeFolder( create=1 )

    if home is not None and not REQUEST.get('noDefaults'):
        members = portal.storage.members
        ids = members.user_defaults.objectIds()
        if ids:
            data = members.user_defaults.manage_copyObjects( ids )
            home.manage_pasteObjects( data )
            home.changeOwnership( username, recursive=1 )

    if home is not None and registered_by_user:
        res = context.portal_catalog.searchResults( path=home.physical_path(), implements='isContentStorage' )
        for r in res:
            ob = r.getObject()
            if ob is None:
                continue
            ob.delLocalRoles( userids=[ registered_by_user ] )

return context.registered( context, REQUEST )
