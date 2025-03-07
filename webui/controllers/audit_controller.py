from sqlalchemy import func,asc

class AuditController:
	def __init__(self,DatasetDao,UserDao,TimeValidatedDao,db):
		self.Dataset = DatasetDao
		self.User = UserDao
		self.TimeValidated = TimeValidatedDao
		self.db = db
		self.users_dict = {}

	def __audit_annotation_smaller_than_duration(self):
		# select tv.user_validated, count(*) as total from TimeValidated as tv, Dataset as ds where tv.id_data = ds.id and ds.duration >  tv.duration group by user_validated order by total;
		results = self.TimeValidated.query.join(self.Dataset,self.Dataset.id == self.TimeValidated.id_data)\
					.with_entities(self.TimeValidated.user_validated,func.count())\
					.filter(self.Dataset.duration > self.TimeValidated.duration).group_by(self.TimeValidated.user_validated).order_by(asc(self.TimeValidated.user_validated)).all()
		
		resutls_dict = {i[0]:i[1] for i in results}
		return resutls_dict

	def __audit_breaks_by_user(self):
		# select user_validated, count(*) as paradas from TimeValidated where duration = 180 group by user_validated order by user_validated;
		# select user_validated, sum(duration)/3600 as horas From TimeValidated where duration < 180 group by user_validated order by user_validated;

		users_breaks = self.TimeValidated.query.join(self.User, self.User.username == self.TimeValidated.user_validated)\
			.with_entities(self.TimeValidated.user_validated,func.count())\
			.filter(self.TimeValidated.duration == 180, self.User.username.ilike('%@%').label('username')).group_by(self.TimeValidated.user_validated).order_by(asc('username')).all()
		
		hours_working = self.TimeValidated.query.join(self.User, self.User.username == self.TimeValidated.user_validated)\
			.with_entities(self.TimeValidated.user_validated,func.sum(self.TimeValidated.duration).label('sum_duration'))\
			.filter(self.TimeValidated.duration < 180, self.User.username.ilike('%@%').label('username')).group_by(self.TimeValidated.user_validated).order_by(asc('username')).all()

		users_breaks_dict = {i[0]:int(i[1]) for i in users_breaks}
		
		hours_working_dict = {i[0]:float(i[1])/3600.0 for i in hours_working}

		
		users_breaks_normalized = {user:value/(hours_working_dict[user]/20.0) for user, value in users_breaks_dict.items()}
		
		return users_breaks_normalized

	def __audit_max_time_worked(self):
		#create temporary table aux1 as select user_validated, year(time_validated) as ano, month(time_validated) as mes, day(time_validated) as dia, 
		#sum(duration)/3600 as total from TimeValidated where duration <= 600 group by user_validated, ano, mes, dia;
		#select user_validated, max(total) as total2 from aux1 group by user_validated order by total2;

		first_query = self.TimeValidated.query.with_entities(self.TimeValidated.user_validated,func.extract('year',self.TimeValidated.time_validated).label('ano'),
							func.extract('month',self.TimeValidated.time_validated).label('mes'),func.extract('day',self.TimeValidated.time_validated).label('dia'),
							func.sum(self.TimeValidated.duration).label('total'))\
							.filter(self.TimeValidated.duration<= 600, self.TimeValidated.user_validated.ilike('%@%')).group_by(self.TimeValidated.user_validated,'ano','mes','dia').subquery()
		
		# o .c significa coluna, entao, .c.total eh a coluna total da subquery
		second_query = self.db.session.query(first_query).with_entities(first_query.c.user_validated,func.max(first_query.c.total/3600.0).label('total2'))\
						.group_by(first_query.c.user_validated).filter(first_query.c.user_validated.ilike('%@%')).order_by(first_query.c.user_validated).all()
		
		second_query_result = {i[0]:float(i[1]) for i in second_query}

		return second_query_result

	def __audit_time_by_user(self):
		#select user_validated, avg(duration) as media from TimeValidated where duration <= 180 group by user_validated order by media;
		users_time = self.TimeValidated.query.join(self.User, self.User.username == self.TimeValidated.user_validated)\
			.with_entities(self.TimeValidated.user_validated,func.avg(self.TimeValidated.duration).label('avg_duration'))\
			.filter(self.TimeValidated.duration<=180, self.User.username.ilike('%@%').label('username')).group_by(self.TimeValidated.user_validated).order_by(asc('username')).all()

		users_time_dict = {i[0]:float(i[1]) for i in users_time}

		return users_time_dict

	def __audit_total_audios_by_user(self):
		# create temporary table aux1 as select user_validated, count(*) as audios, sum(duration)/3600 as horas from TimeValidated where duration < 180 group by user_validated order by audios desc;
		# select *, (audios/horas) as audios_por_hora from aux1 order by audios_por_hora;
		query_result = self.TimeValidated.query.with_entities(self.TimeValidated.user_validated,func.count().label('audios'),func.sum(self.TimeValidated.duration/3600.0).label('horas'))\
						.filter(self.TimeValidated.duration<180).group_by(self.TimeValidated.user_validated).all()
		
		
		query_result_dict = {i[0]:float(i[1]/i[2]) for i in query_result}
		return query_result_dict

	def __append_values_to_key_of_users_dict(self,values_dict,separator=','):
		for user,data in self.users_dict.items():
			string_of_values = data
			if user in values_dict:
				string_of_values += '{}{:.2f}'.format(separator,values_dict[user])
			else:
				string_of_values += '{}0'.format(separator)
			self.users_dict[user] = string_of_values
	
	def generate_audit_report(self):
		result = ''
		users = self.User.query.with_entities(self.User.username).filter(self.User.username.ilike('%@%').label('username')).order_by(asc('username')).all()
		self.users_dict = {key[0]:'' for key in users }
		
		time_by_user_dict = self.__audit_time_by_user()
		breaks_by_user_dict = self.__audit_breaks_by_user()
		max_time_worked = self.__audit_max_time_worked()
		annotation_smaller_than_duration = self.__audit_annotation_smaller_than_duration()
		total_audios_hour_by_user = self.__audit_total_audios_by_user()


		self.__append_values_to_key_of_users_dict(time_by_user_dict,'')
		self.__append_values_to_key_of_users_dict(breaks_by_user_dict)
		self.__append_values_to_key_of_users_dict(max_time_worked)
		self.__append_values_to_key_of_users_dict(annotation_smaller_than_duration)
		self.__append_values_to_key_of_users_dict(total_audios_hour_by_user)

		for user, data in self.users_dict.items():
			result += '{},{};'.format(user,data)
		
		return result




# select tv.user_validated, count(*) as total from TimeValidated as tv, Dataset as ds where tv.id_data = ds.id and ds.duration >  tv.duration + 5 group by user_validated order by total;

# -- total de audios por pessoa

