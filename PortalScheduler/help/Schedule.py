from Interface import Attribute, Base

class Schedule(Base):
	"""
	Task planner    
	"""

	def addTask(self, method, frequency, timeNext=None, title='', args=(), kwargs={}):
		"""
		Add task to schedule.
		method: (method) is a method of object
		timeNext: (DateTime) is a DateTime object
		frequency: (float) task event frequency in seconds
		title: (string)
				
		returns: id of creating task.<br>
		"""

	def delTask(self, taskID):
		"""
		Delete task by given id.
		"""

	def taskPause(self, taskID):
		"""
		Pause task by given id.
		"""
		
	def taskResume(self, taskID):
		"""
		Resume task by given id.
		"""

	def getTaskProperties(self, taskID):
		"""
		Get task properties.
		returns hash like this:
		{'timeNext':timeNext, 'timeLast':timeLast, 'frequency':frequency, 'title':title}
		if there is no task with id - taskID 
		then returns None
		"""
		
	def setTaskProperties(self, taskID, frequency=None, timeNext=None, title=None, physicalPath=None, args=None, kwargs=None):
		"""
		Set task properties.
		if any of property is None then this property will not changed
		if there is no task with id - taskID 
		then raise Exception
		"""
		