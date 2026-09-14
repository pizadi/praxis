from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator
import os
import datetime

id_validator = RegexValidator(r"[0-9]{10}", "Invalid ID")
yob_validator = RegexValidator(r"[0-9]{4}", "Invalid year")
phone_validator = RegexValidator(f"[0-9]+")
# Create your models here.

class Tag(models.Model):
    Name = models.CharField(unique=True, max_length=128)

    def __str__(self):
        return self.Name

    class Meta:
        ordering = ['Name']

class Diagnosis(models.Model):
    Name = models.CharField(unique=True, max_length=128)

    def __str__(self):
        return self.Name

    class Meta:
        ordering = ['Name']

class Patient(models.Model):
    index = models.AutoField(primary_key=True, auto_created=True)
    ID = models.CharField(unique=True, max_length=10, validators=[id_validator])
    First_Name = models.CharField(max_length=128)
    Last_Name = models.CharField(max_length=128)
    Insurance = models.CharField(max_length=128, null=True, blank=True)
    Year_of_Birth = models.CharField(max_length=4, validators=[yob_validator])
    Phone_Number = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    Gender = models.IntegerField(choices=[(0, 'Male'), (1, 'Female')])
    Diagnoses = models.ManyToManyField(Diagnosis, blank=True, related_name='patients')
    Tags = models.ManyToManyField(Tag, blank=True, related_name='patients')

    def __str__(self):
        return f'{self.ID}-{self.First_Name} {self.Last_Name}'

class Appointment(models.Model):
    index = models.AutoField(primary_key=True, auto_created=True)
    Patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    Appointment_Date = models.DateTimeField(default=timezone.now)
    Notes = models.TextField(blank=True)
    CM = models.TextField(blank=True, verbose_name='CM')
    HX = models.TextField(blank=True, verbose_name='Hx')
    PX = models.TextField(blank=True, verbose_name='Px')
    RX = models.TextField(blank=True, verbose_name='Rx')

    def __str__(self):
        return f'[{self.Patient.First_Name} {self.Patient.Last_Name}] {self.Appointment_Date.date()}'


class Transaction(models.Model):
    Related_Appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE)
    id = models.AutoField(primary_key=True, auto_created=True)
    Description = models.CharField(max_length=128)
    Amount = models.BigIntegerField()
    POS = models.BooleanField(default=True)


class Attachfile(models.Model):
    id = models.AutoField(primary_key=True, auto_created=True)
    Appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE)
    Description = models.CharField(max_length=128)
    File = models.FileField(upload_to='patient_files', null=True, blank=True)
    Notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):  
  
        if self.File:
            ext = self.File.name.split('.')[-1]
            self.File.name = f'{self.Appointment.Patient.ID}-{datetime.datetime.now().date()}-{datetime.datetime.now().time()}.{ext}'
      
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.File:
            if os.path.isfile(self.File.path):
                os.remove(self.File.path)

        super().delete(*args, **kwargs)

    def __str__(self):
        return f'[{self.Appointment.Patient.First_Name} {self.Appointment.Patient.Last_Name}] {self.Description} / {self.Appointment.Appointment_Date.date()}'
