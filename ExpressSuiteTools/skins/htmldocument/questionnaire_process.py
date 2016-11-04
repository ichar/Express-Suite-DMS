## Script (Python) "questionnaire_process"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=
##title=process a questionnaire
##
from Products.ExpressSuiteTools.SecureImports import parseDate

REQUEST=context.REQUEST

mailhost = context.MailHost
message='Questionnaire submitted'

catObj = context.portal_metadata.getCategoryById( context.category )

for f in catObj.listAttributeDefinitions():
    if f.Type()=='date' and REQUEST.has_key(f.getId()+'_day'):
        REQUEST.set(f.getId(), parseDate(f.getId(), REQUEST))

mailhost.sendTemplate( template='questionnaire'
                     , mto=context.getQuestEmails('list')
                     , R=REQUEST
                     , cntx=context
                     )

if context.isQuestAction()==1:
    REQUEST.RESPONSE.redirect(context.getQuestAction().absolute_url())
else:
    REQUEST.RESPONSE.redirect(context.absolute_url())

return 1
