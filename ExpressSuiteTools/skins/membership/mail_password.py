## Script (Python) "mail_password"
##title=Mail a user's password
##parameters=userids
REQUEST=context.REQUEST

for userid in userids:
    context.portal_registration.mailPassword( userid, REQUEST )

return context.mail_password_response( context, REQUEST )
