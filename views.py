from django.shortcuts import render, redirect
from django.http import FileResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Prefetch
import psutil
import datetime
from .models import *
from .forms import *
import os
from jalali_date import datetime2jalali, date2jalali
import tarfile
import io

# Create your views here.

def home(request):
    context = {

            }
    return render(request, 'home.html', context)

def default(request):
    return redirect('home')

def icon(request):
    return FileResponse(open('/media/mount/patients/patients/website/favicon.ico', 'rb'))

def bootstrapjs(request):
    return FileResponse(open('/media/mount/patients/patients/website/bootstrap.min.js', 'rb'))


def popperjs(request):
    return FileResponse(open('/media/mount/patients/patients/website/popper.min.js', 'rb'))

def stylesheet(request):
    return FileResponse(open('/media/mount/patients/patients/website/bootstrap.min.css', 'rb'))

def static(request, fl):
    flpath = os.path.join('/home/pi/static', fl)
    print(flpath)
    if os.path.exists(flpath):
        return FileResponse(open(flpath, 'rb'))
    else:
        raise ObjectDoesNotExist()

@login_required
def file_dl(request, filename):
    file_path = os.path.join('patient_files', filename)
    abs_file_path = os.path.abspath(file_path)
    abs_dir = os.path.abspath('patient_files')
    if abs_file_path.startswith(abs_dir) and os.path.exists(file_path):
        response = FileResponse(open(file_path, 'rb'))
        return response
    else:
        return render(request, '404.html', status=404)


@login_required
def searchpatient(request):
    if request.method == 'POST':
        p_form = PatientSearchForm(request.POST)
        if p_form.is_valid():
            data = p_form.cleaned_data
            results = Patient.objects.all()
            selected_diagnoses = data['Diagnoses']
            selected_tags = data['Tags']

            results = results.filter(ID__icontains=data['ID'])
            results = results.filter(First_Name__icontains=data['First_Name'])
            results = results.filter(Last_Name__icontains=data['Last_Name'])

            if selected_diagnoses:
                results = results.prefetch_related(
                        Prefetch('Diagnoses', queryset=Diagnosis.objects.filter(id__in=selected_diagnoses))
                        )

                results = [p for p in results if all(d in p.Diagnoses.all() for d in selected_diagnoses)]

            if selected_tags:
                results = results.prefetch_related(
                        Prefetch('Tags', queryset=Tag.objects.filter(id__in=selected_tags))
                        )

                results = [p for p in results if all(d in p.Tags.all() for d in selected_tags)]



            if len(results) == 0:
                messages.warning(request, 'No patient matched the queries.')

            context = {
                    'form': p_form,
                    'results': results
                    }
        else:
            p_form = PatientSearchForm()
            context = {
                    'form': p_form,
                    'results': []
                    }
    else:
        p_form = PatientSearchForm()
        context = {
                'form': p_form,
                'results': []
                }

    return render(request, 'searchpatient.html', context)

@login_required
def viewpatient(request, patientidx):
    try:
        patient = Patient.objects.get(pk=patientidx)
        appts = Appointment.objects.filter(Patient=patient)
        diagnoses = patient.Diagnoses.all()
        tags = patient.Tags.all()
        all_files = []
        for appointment in appts:
            files = Attachfile.objects.filter(Appointment=appointment)
            all_files.extend(files)

        all_files = sorted(all_files, key=lambda f: f.Appointment.Appointment_Date, reverse=True)

        context = {
                'patient' : patient,
                'appointments' : appts,
                'diagnoses' : diagnoses,
                'tags' : tags,
                'files' : all_files
                }
        return render(request, 'viewpatient.html', context)
    except ObjectDoesNotExist:
        return render(request, '404.html', status=404)

@login_required
def addpatient(request):
    if (request.method == "POST"):
        form = NewPatientForm(request.POST)
        if (form.is_valid()):
            patient = form.save()
            messages.success(request, 'Patient added successfully.')
            id = patient.pk
            return redirect('viewpatient', patientidx=id)
        else:
            messages.warning(request, 'Please check the forms again.')
    else:
        form = NewPatientForm()
    context = {
            'form' : form
            }
    return render(request, 'addpatient.html', context)

@login_required
def deletepatient(request):
    if (request.method == 'POST'):
        try:
            patient = Patient.objects.get(pk=request.POST['index'])
            patient.delete()
            messages.success(request, f'Patient {patient.First_Name} {patient.Last_Name} successfully deleted.')
            return redirect('searchpatient')
        except ObjectDoesNotExist:
            messages.warning(request, f'Patient not found!')
            return redirect('searchpatient')
    else:
        messages.info(request, f'Bad delete request!')
        return redirect('searchpatient')

@login_required
def editpatient(request, patientidx):
    if (request.method == 'POST'):
        try:
            patient = Patient.objects.get(pk=patientidx)
        except ObjectDoesNotExist:
            messages.warning(request, f'Patient not found!')
            return redirect('searchpatient')
        form = NewPatientForm(request.POST, instance=patient)
        if (form.is_valid()):
            form.save()
            messages.success(request, f'Data changed successfully.')
            context = {
                    'form' : form,
                    }
            return redirect('viewpatient', patientidx=patientidx)
        else:
            messages.warning(request, f'Invalid data!')
            context = {
                    'form' : NewPatientForm(instance=patient),
                    }
    else:
        try:
            patient = Patient.objects.get(pk=patientidx)
            form = NewPatientForm(instance=patient)
            context = {
                    'form' : form,
                    }
        except ObjectDoesNotExist:
            messages.warning(request, f'Patient not found!')
            return redirect('viewpatient', patientidx=patientidx)
    return render(request, 'editpatient.html', context)

@login_required
def addappt(request, patientidx):
    if (request.method == 'POST'):
        try:
            patient = Patient.objects.get(pk=patientidx)
        except ObjectDoesNotExist:
            messages.warning(request, f'Patient not found!')
            return redirect('searchpatient')
        form = NewApptForm(request.POST)
        if (form.is_valid()):
            appt = form.save(commit=False)
            appt.Patient = patient
            appt.save()
            messages.success(request, f'Appointment added successfully.')
            return redirect('viewappt', index=appt.pk)
        else:
            messages.warning(request, f'Invalid data!')
            return render(request, 'addappt.html', context)
    else:
        try:
            patient = Patient.objects.get(pk=patientidx)
            form = NewApptForm()
            context = {
                    'form' : form,
                    }
        except ObjectDoesNotExist:
            messages.warning(request, f'Patient not found!')
            return redirect('searchpatient')
    return render(request, 'addappt.html', context)

@login_required
def editappt(request, index):
    if (request.method == 'POST'):
        try:
            appt = Appointment.objects.get(pk=index)
        except ObjectDoesNotExist:
            messages.warning(request, f'Appintment not found!')
            return redirect('searchpatient')
        form = NewApptForm(request.POST, instance=appt)
        if (form.is_valid()):
            form.save()
            messages.success(request, f'Data changed successfully.')
            context = {
                    'form' : form,
                    }
            return redirect('viewappt', index=index)
        else:
            messages.warning(request, f'Invalid data!')
            context = {
                    'form' : NewApptForm(instance=appt),
                    }
    else:
        try:
            appt = Appointment.objects.get(pk=index)
            form = NewApptForm(instance=appt)
            context = {
                    'form' : form,
                    }
        except ObjectDoesNotExist:
            messages.warning(request, f'Appointment not found!')
            return redirect('searchpatient')
    return render(request, 'editappt.html', context)


@login_required
def viewappt(request, index):
    try:
        appt = Appointment.objects.get(pk=index)
        patient = appt.Patient
        files = Attachfile.objects.filter(Appointment=appt)
        transactions = Transaction.objects.filter(Related_Appointment=appt)
        context = {
                'patient' : patient,
                'appt' : appt,
                'files' : files,
                'transactions' : transactions
                }
        return render(request, 'viewappt.html', context)
    except ObjectDoesNotExist:
        messages.warning(request, 'Appointment not found!')
        return redirect('searchpatient')

@login_required
def delappt(request):
    if (request.method == 'POST'):
        try:
            appt = Appointment.objects.get(pk=int(request.POST['index']))
            patient = appt.Patient
            appt.delete()
            messages.success(request, 'Appointment deleted successfully.')
            return redirect('viewpatient', patientidx=patient.index)
        except ObjectDoesNotExist:
            messages.warning(request, 'Appointment not found!')
            return redirect('searchpatient')
    else:
        return redirect('searchpatient')

@login_required
def addfile(request, index):
    if (request.method == 'POST'):
        try:
            appt = Appointment.objects.get(pk=index)
        except ObjectDoesNotExist:
            messages.warning(request, f'Appointment not found!')
            return redirect('searchpatient')
        form = NewFileForm(request.POST, request.FILES)
        if (form.is_valid()):
            file = form.save(commit=False)
            file.Appointment = appt
            file.save()
            messages.success(request, f'File added successfully.')
            return redirect('viewappt', index=index)
        else:
            print(request.FILES)
            messages.warning(request, f'Invalid data!')
            context = {
                    'form' : NewFileForm(),
                    }
    else:
        try:
            appt = Appointment.objects.get(pk=index)
            form = NewFileForm()
            context = {
                    'appt' : appt,
                    'form' : form,
                    }
        except ObjectDoesNotExist:
            messages.warning(request, f'Appointment not found!')
            return redirect('viewappt', index=index)
    return render(request, 'addfile.html', context)

@login_required
def delfile(request):
    if (request.method == 'POST'):
        try:
            file = Attachfile.objects.get(pk=request.POST['id'])
            appt = file.Appointment
            file.delete()
            messages.success(request, 'File deleted successfully.')
            return redirect('viewappt',index=appt.index)
        except ObjectDoesNotExist:
            messages.warning(request, 'File not found!')
            return redirect('searchpatient')
    else:
        return redirect('searchpatient')

@login_required
def diagnoses(request):
    diags = Diagnosis.objects.all()
    form = NewDiagnosis()
    context = {
            'form' : form,
            'diagnoses' : diags
            }
    return render(request, 'diagnoses.html', context)

@login_required
def renamediagnosis(request, id):
    if (request.method == 'POST'):
        try:
            diag = Diagnosis.objects.get(pk=id)
            diag.Name = request.POST['Name']
            diag.save()
            messages.success(request, 'Diagnosis renamed.')
            return redirect('diagnoses')
        except:
            messages.warning(request, 'Diagnosis not found!')
            return redirect('diagnoses')
    else:
        diag = Diagnosis.objects.get(pk=id)
        print(diag)
        form = DiagnosisRename(instance=diag)
        context = {
                'form' : form
                }
        return render(request, 'diagnosisrename.html', context)

@login_required
def deletediagnosis(request):
    if (request.method == 'POST'):
        try:
            diag = Diagnosis.objects.get(pk=request.POST['id'])
            diag.delete()
            messages.success(request, 'Diagnosis removed.')
            return redirect('diagnoses')
        except:
            messages.warning(request, 'Diagnosis not found!')
    return redirect('diagnoses')

@login_required
def newdiagnosis(request):
    if (request.method == 'POST'):
        try:
            form = NewDiagnosis(request.POST)
            if (form.is_valid()):
                form.save()
                messages.success(request, 'Diagnosis added.')
            else:
                messages.warning(request, 'Could not add diagnosis.')
        except:
            messages.warning(request, 'Diagnosis not found!')
    return redirect('diagnoses')


@login_required
def addpayment(request, index):
    if (request.method == 'POST'):
        try:
            appt = Appointment.objects.get(pk=index)
        except ObjectDoesNotExist:
            messages.warning(request, f'Appointment not found!')
            return redirect('searchpatient')
        form = NewTransaction(request.POST)
        if (form.is_valid()):
            taction = form.save(commit=False)
            taction.Related_Appointment = appt
            taction.save()
            messages.success(request, f'Transaction added successfully.')
            return redirect('viewappt', index=index)
        else:
            messages.warning(request, f'Invalid data!')
            context = {
                    'form' : NewTransaction(),
                    }
    else:
        try:
            appt = Appointment.objects.get(pk=index)
            form = NewTransaction()
            context = {
                    'appt' : appt,
                    'form' : form,
                    }
        except ObjectDoesNotExist:
            messages.warning(request, f'Appointment not found!')
            return redirect('viewappt', index=index)
    return render(request, 'addpayment.html', context)

@login_required
def delpayment(request):
    if (request.method == 'POST'):
        try:
            taction = Transaction.objects.get(pk=request.POST['id'])
            appt = taction.Related_Appointment
            taction.delete()
            messages.success(request, 'Transaction deleted successfully.')
            return redirect('viewappt',index=appt.index)
        except ObjectDoesNotExist:
            messages.warning(request, 'Transaction not found!')
            return redirect('searchpatient')
    else:
        return redirect('searchpatient')

@login_required
def stats(request):
    storage = psutil.disk_usage('/')
    ram = psutil.virtual_memory()
    today = datetime.date.today()
    start_date = datetime.datetime.combine(today, datetime.time.min)
    end_date = datetime.datetime.combine(today, datetime.time.max)

    context = {
        'storage' : storage,
        'ram' : ram
    }
    if (request.method == 'POST'):
        form = DateRangeForm(request.POST)
        if (form.is_valid()):
            start_date = start_date = datetime.datetime.combine(form.cleaned_data['start_date'], datetime.time.min)
            end_date = datetime.datetime.combine(form.cleaned_data['end_date'], datetime.time.max)
            if (start_date > end_date):           
                start_date = datetime.datetime.combine(today, datetime.time.min)
                end_date = datetime.datetime.combine(today, datetime.time.max)   
                messages.warning(request, 'Invalid data.')
        else:
            messages.warning(request, 'Invalid data.')
        context['form'] = DateRangeForm(initial={'start_date': start_date, 'end_date': end_date})
    else:
        context['form'] = DateRangeForm(initial={'start_date': start_date, 'end_date': end_date})
        
    appointments = Appointment.objects.filter(Appointment_Date__range=[start_date, end_date])
    transactions = Transaction.objects.filter(Related_Appointment__Appointment_Date__range=[start_date, end_date])    
    num_appointments = appointments.count()

    transactions_by_description = (transactions.values('Description').annotate(num=Count('id'), value=Sum('Amount')))
    taction_all = transactions.aggregate(num=Count('id'), value=Sum('Amount'))
    taction_pos = transactions.filter(POS=True).aggregate(num=Count('id'), value=Sum('Amount'))
    taction_cash = transactions.filter(POS=False).aggregate(num=Count('id'), value=Sum('Amount'))

    context['appointments'] = appointments
    context['transactions'] = transactions
    context['start_date'] = start_date
    context['end_date'] = end_date
    context['num_appointments'] = num_appointments
    context['transactions_by_description'] = transactions_by_description
    context['taction_all'] = taction_all
    context['taction_pos'] = taction_pos
    context['taction_cash'] = taction_cash
    return render(request, 'stats.html', context)

@login_required
def editfile(request, id):
    if (request.method == 'POST'):
        try:
            file = Attachfile.objects.get(pk=id)
            appt = file.Appointment
        except ObjectDoesNotExist:
            messages.warning(request, f'File not found!')
            return redirect('searchpatient')
        form = EditFileForm(request.POST, request.FILES, instance=file)
        if (form.is_valid()):
            Attachfile.objects.filter(id=id).update(Description=form.cleaned_data['Description'], Notes=form.cleaned_data['Notes'])
            messages.success(request, f'File changed successfully.')
            context = {
                    'form' : form,
                    }
            return redirect('viewappt', index=appt.index)
        else:
            messages.warning(request, f'Invalid data!')
            context = {
                    'form' : EditFileForm(instance=appt),
                    }
    else:
        try:
            file = Attachfile.objects.get(pk=id)
            form = EditFileForm(instance=file)
            context = {
                    'form' : form,
                    }
        except ObjectDoesNotExist:
            messages.warning(request, f'File not found!')
            return redirect('searchpatient')
    return render(request, 'editfile.html', context)

@login_required
def latestappts(request):
    today = datetime.date.today()
    start_date = min(datetime.datetime.combine(today, datetime.time.min), datetime.datetime.now() - datetime.timedelta(hours=24))
    end_date = datetime.datetime.combine(today, datetime.time.max)
    appointments = Appointment.objects.filter(Appointment_Date__range=[start_date, end_date]).order_by('Appointment_Date').reverse()
    context = {
        'appointments' : appointments,
        'current_date': today,
    }
    return render(request, 'latestappts.html', context)

@login_required
def dateappts(request, year, month, day):
    date = datetime.datetime(year=year, month=month, day=day).date()
    start_date = datetime.datetime.combine(date, datetime.time.min)
    end_date = datetime.datetime.combine(date, datetime.time.max)
    appointments = Appointment.objects.filter(Appointment_Date__range=[start_date, end_date]).order_by('Appointment_Date').reverse()
    context = {
        'appointments' : appointments,
        'current_date': date,
    }
    return render(request, 'dateappts.html', context)



@login_required
def tags(request):
    tags = Tag.objects.all()
    form = NewTag()
    context = {
            'form' : form,
            'tags' : tags
            }
    return render(request, 'tags.html', context)

@login_required
def renametag(request, id):
    if (request.method == 'POST'):
        try:
            tag = Tag.objects.get(pk=id)
            tag.Name = request.POST['Name']
            tag.save()
            messages.success(request, 'Tag renamed.')
            return redirect('tags')
        except:
            messages.warning(request, 'Tag not found!')
            return redirect('tags')
    else:
        tag = Tag.objects.get(pk=id)
        print(tag)
        form = TagRename(instance=tag)
        context = {
                'form' : form
                }
        return render(request, 'tagrename.html', context)

@login_required
def deletetag(request):
    if (request.method == 'POST'):
        try:
            tag = Tag.objects.get(pk=request.POST['id'])
            tag.delete()
            messages.success(request, 'Tag removed.')
            return redirect('tags')
        except:
            messages.warning(request, 'Tag not found!')
    return redirect('tags')

@login_required
def newtag(request):
    if (request.method == 'POST'):
        try:
            form = NewTag(request.POST)
            if (form.is_valid()):
                form.save()
                messages.success(request, 'Tag added.')
            else:
                messages.warning(request, 'Could not add tag.')
        except:
            messages.warning(request, 'Tag not found!')
    return redirect('tags')

@login_required
def backup_dl(request):
    files = ['db.sqlite3', 'README.txt']
    buffer = io.BytesIO()
    with tarfile.open(mode='w:gz', fileobj=buffer) as file:
        for path in files:
            file.add(path, arcname=path.split('/')[-1])

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/gzip')
    response['Content-Disposition'] = f'attachment; filename=backup-{datetime.datetime.now().date()}.tar.gz'
    return response

@login_required
def fullbackup_dl(request):
    files = [
            '/home/pi/conf',
            '/home/pi/patvenv',
            '/media/mount/patients'
            ]
    buffer = io.BytesIO()
    with tarfile.open(mode='w:gz', fileobj=buffer) as file:
        for path in files:
            file.add(path, arcname=path.split('/')[-1])

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/gzip')
    response['Content-Disposition'] = f'attachment; filename=fullbackup-{datetime.datetime.now().date()}.tar.gz'
    return response
