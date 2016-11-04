"""
 Setting up recurrring events with temporal expressions
 ------------------------------------------------------
 Temporal expressions are based on a simple idea originating 
 from the Martin Fowler's "Recurring Events Pattern", 
 http://www.martinfowler.com/apsupp/recurring.pdf. In general, 
 almost every recurring event occurence scheme can be described in terms 
 of combination of a few basic objects so each element represents a 
 small part of the whole complex (although not complicated) expression.

 Thus, we have a bunch of classes with the common interface inherited from the
 TemporalExpression base class. DayInMonthTE, MonthInYearTE, DateTimeTE class 
 instances can represent any recurrent event occuring in a month, year or the 
 whole epoch respectively. DateRangeTE class provides us with the incredible
 ability to set the continuous date and time range for the event occurence
 period.

 Unfortunately there is no much use of these objects since they are not combined 
 together to form more complex expressions than just a single condition. Therefore
 we would like to have some way to unify and intersect a set of the temporal 
 expressions. UnionTE and IntersectionTE classes are already here for such 
 honourable purposes.

 It is always possible to check whether it is the right time to start the particular 
 event. All you have to do is to create a temporal expression object and then call 
 it's 'includes' method.
 
 Examples::
 
   Every Second Monday of the month:
   
     DayInMonthTE(0, 2)

   Every last Tuesday of the month:

     DayInMonthTE(1, -1)

   Every second Wednesday and Friday in March, April and June from 15/03/2003 
   till 7/05/2003:
 
     te = IntersectionTE()
     te.addElement(DayInMonthTE([2, 4], 2)) # Every second Wednesday and Friday
     te.addElement(MonthInYearTE([2, 3, 5])) # ... in March, April and June
     te.addElement(DateRangeTE( DateTime('15/03/2003')
                              , DateTime('7/05/2003')
                              )) # ... from 15/03/2003 till 7/05/2003

   Event occures every Sunday but also in 30/12/2003:

    te = UnionTE()
    te.addElement(DayInMonth(6))
    te.addElement(DateTimeTE(DateTime('30/12/2003')))

$Id: TemporalExpressions.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 10/12/2007 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from types import StringType, IntType
from mx.DateTime import DateTime, DateTimeType, DateTimeFrom, RelativeDateTime, now, DateTimeFromAbsDateTime
from DateTime import DateTime as ZopeDateTime

from Products.CMFCore.utils import getToolByName

from Products.ExpressSuiteTools.SimpleObjects import InstanceBase
from Products.ExpressSuiteTools.Exceptions import SimpleError
from Products.ExpressSuiteTools.Utils import translate

Weekday = [ 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su' ]
Month = list( ZopeDateTime._months_a )


class TemporalExpression( InstanceBase ):
    """
        Abstract temporal expression class
    """
    __allow_access_to_unprotected_subobjects__ = 1

    start_date = None
    end_date = None

    def nextOccurence( self ):
        """
          Returns the next event occurence date.

          Result:

            DateTime instance
        """
        pass

    def listOccurences( self, range_min_date, range_max_date, find_first=None ):
        """
            Returns the list of event occuring dates.

            Arguments:

                'range_min_date' -- lower date range limit.

                'range_max_date' -- higher date range limit.

            Result:

                List of DateTime instances.
        """
        pass

    def getEffectiveDate( self ):
        start = now()
        if self.start_date and self.start_date > start:
            start = self.start_date
        return start

    def getRealDate( self ):
        return self.start_date

    def __str__( self ):
        return 'unknown'

class YearlyTE( TemporalExpression ):
    """
    """
    expression_type = "Yearly"

    def __init__(self, years_period, months, start_date, end_date=None ):
        """
        """
        simple_assert( years_period > 0, 'Years period must be a positive integer, not %s.' % years_period )
        self.years_period = years_period

        months.sort()
        self.months = months
        self.start_date = datify( start_date )
        self.end_date = end_date and datify( end_date )

    def nextOccurence( self ):
        start = self.getEffectiveDate()
        return self.listOccurences(start, start + RelativeDateTime(years=self.years_period), 1)

    def listOccurences( self, range_min_date, range_max_date, find_first=None ):
        results = []
        distance = 0
        occurence = start_date = self.start_date
        if self.end_date and self.end_date < range_max_date:
            range_max_date = self.end_date

        while occurence < range_max_date:
            for month in self.months:
                occurence = start_date + RelativeDateTime(years=distance, month=month)
                if range_min_date <= occurence <= range_max_date:
                    if find_first: return occurence
                    results.append(occurence)

            distance += self.years_period

        return results

    def __str__( self ):

        num = self.years_period
        if num / 10 % 10 != 1 and num % 10 == 1:
           year_translation = translate( self, 'year' )
        elif num / 10 % 10 != 1 and num % 10 in [2,3,4]:
           year_translation = translate( self, 'year.plural')
        else:
           year_translation = translate( self, 'years')

        years_period = '%d %s' % (num, year_translation)
   
        data = { 'time': self.start_date.strftime('%X')
               , 'day': self.start_date.strftime('%d')
               , 'months': ', '.join( [ translate(self, 'prepositional.%s' % Month[i]) for i in self.months ] )
               , 'years_period': years_period
               }

        message = translate( self, 'At %(time)s on day %(day)s in the %(months)s of every %(years_period)s' ) % data
        return apply_range_message( self, message, self.start_date, self.end_date )

class MonthlyByDayTE( TemporalExpression ):
    """
        Repeats the event every month on a given days and weeks.
    """
    expression_type = "Monthly by day"

    def __init__( self, months_period, weeks, weekdays, start_date, end_date=None ):
        """
          Initializes the class instance.

          Arguments:

          Note:

        """
        self.start_date = datify( start_date )
        self.end_date = end_date and datify( end_date )
        self.weekdays = weekdays

        simple_assert( months_period > 0, 'Months period must be a positive integer, not %s.' % months_period )
        self.months_period = months_period
        self.weeks = weeks

    def nextOccurence( self ):
        start = self.getEffectiveDate()
        return self.listOccurences( start, start + RelativeDateTime(months=self.months_period), 1 )

    def listOccurences( self, range_min_date, range_max_date, find_first=None ):
        results = []
        distance = 0
        range_min_date = datify( range_min_date )
        range_max_date = datify( range_max_date )
        occurence = self.start_date

        if range_min_date < self.start_date:
            range_min_date = self.start_date
        if self.end_date and self.end_date < range_max_date:
            range_max_date = self.end_date

        while occurence < range_max_date:
            for week in self.weeks:
                assert -5 < week < 5
                for weekday in self.weekdays:
                     assert weekday < 7
                     occurence = self.start_date + RelativeDateTime( months=distance, weekday=(weekday, week) )
                     if range_min_date <= occurence <= range_max_date and occurence not in results:
                        if find_first:
                            return occurence
                        results.append( occurence )

            distance += self.months_period

        results.sort()
        return results

    def __str__( self ):
        data = { 'time': self.start_date.strftime('%X'),
                 'weeks': ', '.join( map( str, self.weeks ) ),
                 'weekdays': ', '.join( [ translate( self, 'accusative.%s' % Weekday[i] ) for i in self.weekdays] ),
                 'months_period': self.months_period,
               }

        message = translate( self, 'At %(time)s on the %(weeks)s %(weekdays)s of every %(months_period)s month' ) % data
        return apply_range_message( self, message, self.start_date, self.end_date )

class MonthlyByDateTE( TemporalExpression ):
    """
    """
    expression_type = "Monthly by date"

    def __init__( self, months_period, days, start_date, end_date=None ):
        """
            Initializes the class instance
        """
        self.start_date = datify( start_date )
        self.end_date = end_date and datify( end_date )

        simple_assert( months_period > 0, 'Months period must be a positive integer, not %s.' % months_period )
        self.months_period = months_period
        self.days = days

    def nextOccurence( self ):
        start = self.getEffectiveDate()
        return self.listOccurences( start, start + RelativeDateTime(months=self.months_period), 1 )

    def listOccurences( self, range_min_date, range_max_date, find_first=None ):
        results = []
        distance = 0
        range_min_date = datify( range_min_date )
        range_max_date = datify( range_max_date )
        occurence = self.start_date

        if range_min_date < self.start_date:
            range_min_date = self.start_date
        if self.end_date and self.end_date < range_max_date:
            range_max_date = self.end_date

        while occurence < range_max_date:
            for day in self.days:
                occurence_month = self.start_date + RelativeDateTime(months=distance)
                if day > occurence_month.days_in_month:
                    continue

                occurence = self.start_date + RelativeDateTime(months=distance, day=day)
                if range_min_date <= occurence < range_max_date and occurence not in results:
                    if find_first:
                        return occurence
                    results.append( occurence )

            distance += self.months_period

        results.sort()
        return results

    def __str__( self ):
        data = { 'time': self.start_date.strftime('%X'),
                 'days': ', '.join( [ str( i ) for i in self.days ] ),
                 'months_period': self.months_period,
               }

        message = translate( self, 'At %(time)s on day %(days)s of every %(months_period)s month' ) % data
        return apply_range_message( self, message, self.start_date, self.end_date )

class WeeklyTE( TemporalExpression ):
    """
    """
    expression_type = "Weekly"

    def __init__( self, weeks_period, week_days, start_date, end_date=None ):
        """
          Initializes the class instance.

        """
        self.start_date = datify( start_date )
        self.end_date = end_date and datify( end_date )
        
        if type(week_days) is IntType:
            week_days = [week_days]
        self.week_days = week_days

        simple_assert( weeks_period, 'Weeks period must be a positive integer, not %s.' % weeks_period )
        self.weeks_period = weeks_period

    def nextOccurence( self ):
        start = self.getEffectiveDate()
        return self.listOccurences( start, start + RelativeDateTime(weeks=self.weeks_period), 1 )

    def listOccurences( self, range_min_date, range_max_date, find_first=None  ):
        results = []
        distance = 0
        range_min_date = datify( range_min_date )
        range_max_date = datify( range_max_date )
        occurence = self.start_date

        if range_min_date < self.start_date:
            range_min_date = self.start_date
        if self.end_date and self.end_date < range_max_date:
            range_max_date = self.end_date

        while occurence < range_max_date:
            for week_day in self.week_days:
                occurence = self.start_date + RelativeDateTime( weeks=distance, weekday=(week_day,0) )
                if range_min_date <= occurence <= range_max_date and occurence not in results:
                    if find_first: return occurence
                    results.append( occurence )

            distance += self.weeks_period

        results.sort()                                   
        return results

    def __str__( self ):
        data = { 'time': self.start_date.strftime('%X'), 
                 'week_days': ', '.join( [ translate( self, 'accusative.%s' % Weekday[i] ) for i in self.week_days] ), 
                 'start_date': self.start_date.strftime('%x'),
               }
        if self.weeks_period > 1:
            message = 'At %(time)s every %(week_days)s of every %(weeks_period)s weeks'
            data[ 'weeks_period' ] = self.weeks_period
        else:
            message = 'Weekly at %(time)s every %(week_days)s'

        message = translate( self, message ) % data
        return apply_range_message( self, message, self.start_date, self.end_date )

class DateTimeTE( TemporalExpression ):
    """
        One time event
    """
    expression_type = "DateTime"

    def __init__( self, date_time ):
        """
            Initializes the class instance

            Arguments:

                'date_time' -- DateTime object.
        """
        self.date_time = datify( date_time )

    def nextOccurence( self ):
        date_time = self.getRealDate()
        try:
            if date_time > now(): return date_time
        except: pass
        return None

    def listOccurences( self, range_min_date, range_max_date ):
        range_min_date = datify( range_min_date )
        range_max_date = datify( range_max_date )
        date_time = self.getRealDate()
        if date_time is not None:
            if range_min_date <= date_time <= range_max_date:
                return [ date_time ]
        return None

    def getRealDate( self ):
        return getattr( self, 'date_time', None )

    def __str__( self ):
        date_time = self.getRealDate()
        if date_time is None:
            return 'Bad date time'
        data = { 'time': date_time.strftime('%X'), 'date': date_time.strftime('%x') }
        return translate( self, 'At %(time)s on %(date)s' ) % data

class DailyTE( TemporalExpression ):
    """
        Event has to be executed every day in a particular time.
    """
    expression_type = "Daily"

    def __init__( self, hour, minute, second, days, start_date=None, end_date=None ):
        """
          Initializes the class instance.

          Arguments:

            'hour', 'minute', 'second' -- time to start an event.
        """
        self.hour = hour
        self.minute = minute
        self.second = second

        simple_assert( days > 0, 'Positive days value expected' )
        self.days = days

        self.start_date = start_date and datify( start_date )
        self.end_date = end_date and datify( end_date )

    def nextOccurence( self ):
        try:
            if self.days > 0:
                start = self.getEffectiveDate()
                return self.listOccurences( start, start + RelativeDateTime(days=self.days), 1 )
        except: pass
        return None

    def listOccurences( self, range_min_date, range_max_date, find_first=None ):
        range_min_date = datify( range_min_date )
        range_max_date = datify( range_max_date )

        if self.start_date and self.start_date > range_min_date:
            range_min_date = self.start_date
        if self.end_date and self.end_date < range_max_date:
            range_max_date = self.end_date

        occurence = DateTimeFromAbsDateTime(range_min_date.absdate) + \
                    RelativeDateTime( hours=self.hour,
                                      minutes=self.minute,
                                      seconds=self.second
                                    )
        results = []
        while occurence <= range_max_date:
            if occurence >= range_min_date:
                if find_first:
                    return occurence
                results.append( occurence )

            occurence += RelativeDateTime(days=self.days)

        return results

    def __str__(self):
        try:
            data = { 'hour': self.hour, 'minute': self.minute, 'second': self.second, }
        except: return ''
        if self.days > 1:
            message = translate( self,  'At %(hour)02d:%(minute)02d:%(second)02d every %(days)d day(s)' )
            data[ 'days' ] = self.days 
        else:
            message = translate( self,  'Daily at %(hour)02d:%(minute)02d:%(second)02d' )
        return apply_range_message( self, message % data, self.start_date, self.end_date )

class UniformIntervalTE( TemporalExpression ):
    """
    """
    expression_type = "Uniform interval"

    def __init__( self, seconds, start_date=None, end_date=None ):
        """
          Initializes the class instance.

          Arguments:

          # XXX Allow minutes, hours, etc.
        """
        self.seconds = seconds
        if start_date is None:
            start_date = now()
        self.start_date = datify( start_date )
        self.end_date = end_date and datify( end_date )

    def nextOccurence( self ):
        start = self.getEffectiveDate()
        return self.listOccurences( start, start + RelativeDateTime(seconds=self.seconds), 1 )

    def listOccurences( self, range_min_date, range_max_date, find_first=None ):
        results = []
        distance = 0
        range_min_date = datify( range_min_date )
        range_max_date = datify( range_max_date )
        occurence = self.start_date

        if self.start_date and self.start_date > range_min_date:
            range_min_date = self.start_date
        if self.end_date and self.end_date < range_max_date:
            range_max_date = self.end_date

        while occurence < range_max_date:
            occurence = self.start_date + RelativeDateTime( seconds=distance )
            if range_min_date <= occurence <= range_max_date and occurence not in results:
                if find_first: return occurence
                results.append( occurence )

            distance += self.seconds

        results.sort()
        return results

    def __str__(self):
        message = translate( self, 'Every %d seconds' ) % self.seconds
        return apply_range_message( self, message, self.start_date, self.end_date )

# XXX TODO

class DateRangeTE( TemporalExpression ):
    """
        Event occures in a particular range in a year
    """
    expression_type = "Date range"

    def __init__( self, range_min_date, range_max_date ):
        """
            Initializes the class instance

            Arguments:

                'range_min_date' -- lower date range limit.

                'range_max_date' -- higher date range limit.
        """
        self.range_min_date = datify( range_min_date )
        self.range_max_date = datify( range_max_date )

class SetTE( TemporalExpression ):
    """
        Base class for the temporal expressions set.
    """
    expression_type = "Set"

    def __init__( self, elements=[] ):
        """
            Initializes the class instance.

            Arguments:

                'elements' -- a list of TimeExpression class instances.
        """
        self.elements = elements

    def addElement( self, temporal_expr ):
        """
            Adds a new temporal expression element.

            Arguments:

                'element' -- TemporalExpression class instance.
        """
        self.elements.append( temporal_expr )
        self._p_changed = 1
        
    def listElements(self, wrapped=False):
        return wrapped and [ e.__of__(self) for e in self.elements ] or list(self.elements)

    def __str__(self):
        return '\n'.join( [ translate(self, self.expression_type) ] + map( str, self.listElements(True) ) )

class UnionTE( SetTE ):
    """
        Temporal expressions unification
    """
    expression_type = "Union"

    def includes( self, date ):
        # Check for *any* element to return True
        for element in self.elements:
            if element.includes(date):
               return 1

class IntersectionTE( SetTE ):
    """
        Temporal expressions intersection
    """
    expression_type = "Intersection"

    def includes( self, date ):
        # Check for *every* element to return True
        for element in self.elements:
            if not element.includes(date):
               return 0
        return 1

#
# Helper functions

def datify( date_time ):
    if type(date_time) is not DateTimeType:
        return DateTimeFrom( date_time )
    return date_time

def apply_range_message( self, message, start_date, end_date ):
    if start_date:
        suffix = translate( self, ', starting %s' )
        message += suffix % start_date.strftime('%x %X')
        if end_date:
            suffix = translate( self, ' and ending %s' )
            message += suffix % end_date.strftime('%x %X')

    return message

def simple_assert( expr, message='' ):
    if not expr:
        raise SimpleError, message
