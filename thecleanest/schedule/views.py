from __future__ import division

import math
from datetime import datetime, date, timedelta
from itertools import islice, takewhile
import dateutil.parser
from django.db.models import Count
from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.shortcuts import render_to_response, render, get_object_or_404, redirect
from django.conf import settings
from django.core.serializers import serialize, deserialize
from django.core.urlresolvers import reverse
from schedule.models import Assignment, Debit, Credit, NamelessWorker
from schedule.workdays import date_range, weekdays, is_workday, is_holiday, is_weekend
from notifications.models import Bone, Nudge
import calendar

def index(request):

    current_assignment = Assignment.objects.current_assignment()

    today = date.today()
    today_weekday = calendar.weekday(today.year, today.month, today.day)
    today_range = (datetime(today.year, today.month, today.day, 0, 0, 0),
                   datetime(today.year, today.month, today.day, 23, 59, 59))
    monday = date.today() - timedelta(days=today_weekday)
    friday = monday + timedelta(days=12)
    two_weeks = list(weekdays(date_range(monday, friday)))

    assignments = Assignment.objects.filter(date__gte=monday).order_by('date')[:10]
    assignments_by_date = dict(((a.date, a) for a in assignments))
    week1_assignments = [assignments_by_date.get(dt) for dt in two_weeks[0:5]]
    week2_assignments = [assignments_by_date.get(dt) for dt in two_weeks[5:10]]

    bone_count = Bone.objects.filter(timestamp__range=today_range).count()
    nudge_count = Nudge.objects.filter(timestamp__range=today_range).count()

    context = {
        'today': str(today),
        'today_date': today,
        'monday': str(monday),
        'assignments': assignments,
        'week1_assignments': week1_assignments,
        'week2_assignments': week2_assignments,
        'bone_count': bone_count,
        'nudge_count': nudge_count,
        'current_assignment': current_assignment,
    }

    return render(request, "index.html", context)

def full_schedule(request):

    today = date.today()
    last_week = today - timedelta(days=7)
    assignments = Assignment.objects.filter(date__gte=last_week).order_by('date')

    context = {'assignments': assignments, 'today': today}

    return render(request, "schedule_full.html", context)

def frequency(request):
    workers = NamelessWorker.objects.annotate(cnt=Count('assignments')).order_by('-cnt')
    context = {'workers': workers}
    return render(request, 'counts.html', context)

def eligibles(request, date):
    date = dateutil.parser.parse(date).date()
    if not is_workday(date):
        return redirect(reverse("non_workday", kwargs={'date': date.strftime("%Y-%m-%d")}))

    assignment = get_object_or_404(Assignment, date=date)
    eligibles = list(assignment.eligible_defer_targets())
    min_deferral_weight = min([w.deferral_weight() for w in eligibles])

    return render_to_response('eligibles.html', {
        'date': date,
        'eligibles': eligibles,
        'min_deferral_weight': min_deferral_weight,
        'norm_coeff': 1 / min_deferral_weight,
        'assigned': assignment.worker if assignment else None
    })

def non_workday(request, date):
    date = dateutil.parser.parse(date).date()
    if is_workday(date):
        raise Http404()

    context = {
        'holiday': is_holiday(date),
        'weekend': is_weekend(date)
    }
    return render(request, "non-workday.html", context)

def hall_of_fame(request):

    most_boned = NamelessWorker.objects.annotate(num_bones=Count('bones')).filter(num_bones__gt=0).order_by('-num_bones')[:10]

    context = {
        'most_boned': most_boned,
    }

    return render(request, 'hall_of_fame.html', context)

def hall_of_shame(request):


    workers = NamelessWorker.objects.all()
    excused = workers.filter(email__in=getattr(settings, 'EXCUSED', []))
    most_deferred = sorted((w for w in workers if w.balance() < 0),
                            key=lambda w: w.balance())
    most_nudged = NamelessWorker.objects.annotate(num_nudges=Count('nudges')).filter(num_nudges__gt=0).order_by('-num_nudges')[:10]

    context = {
        'most_deferred': most_deferred,
        'most_nudged': most_nudged,
        'excused': excused,
    }

    return render(request, 'hall_of_shame.html', context)

def assignment_detail(request, assignment_id):

    assignment = get_object_or_404(Assignment, pk=assignment_id)

    context = {
        'assignment': assignment,
        'debits': Debit.objects.filter(skipped_assignment=assignment).select_related(),
        'credits': Credit.objects.filter(skipped_date=assignment.date)
    }

    return render(request, 'assignment_detail.html', context)

def assignment_detail_by_date(request, date):
    date = dateutil.parser.parse(date).date()
    if not is_workday(date):
        return redirect(reverse("non_workday", kwargs={'date': date.strftime("%Y-%m-%d")}))

    assignment = get_object_or_404(Assignment, date=date)
    return assignment_detail(request, assignment.id)

def defer_assignment(request, defer_code):

    try:

        assignment = Assignment.objects.get(defer_code=defer_code)

        if request.method == 'POST':
            assignment.defer()
            return HttpResponseRedirect('/')

    except Assignment.DoesNotExist:
        assignment = None

    return render(request, 'defer.html', {'assignment': assignment})

def worker_detail(request, worker_id):

    worker = get_object_or_404(NamelessWorker, pk=worker_id)

    context = {
        'worker': worker,
        'debits': Debit.objects.filter(worker=worker).select_related(),
    }

    return render(request, 'worker_detail.html', context)


def current_schedule(request):
    # Get current and future assignments
    assignment = Assignment.objects.current_assignment()
    today = date.today()
    today_weekday = calendar.weekday(today.year, today.month, today.day)
    today_range = (datetime(today.year, today.month, today.day, 0, 0, 0),
                   datetime(today.year, today.month, today.day, 23, 59, 59))
    monday = date.today() - timedelta(days=today_weekday)
    def assignment_for_day(day):
        try:
            return Assignment.objects.get(date=day)
        except Assignment.DoesNotExist:
            return None
    def day_info(day):
        return { 'assignment': assignment_for_day(day),
                 'is_workday': 1 if is_workday(day) else 0 }
    days = map(day_info, list(weekdays(date_range(monday, monday + timedelta(days=12)))))
    weeks = [days[x:x+5] for x in range(0, len(days), 5)]
    bone_count = Bone.objects.filter(timestamp__range=today_range).count()
    nudge_count = Nudge.objects.filter(timestamp__range=today_range).count()

    return render_to_response('schedule.html', {
                                  'today': str(today),
                                  'monday': str(monday),
                                  'assignments': assignments,
                                  'weeks': weeks,
                                  'current_assignment': assignment,
                                  'bone_count': bone_count,
                                  'week1': range(0, 5),
                                  'week2': range(5, 10),
                                  'nudge_count': nudge_count
                              })

def kitchen(request):
    assignment = Assignment.objects.current_assignment()
    return render_to_response('kitchen.html', {
        'today': date.today(),
        'worker': assignment.worker if assignment else None
    })

def assignments(request):
    assignments = Assignment.objects.all()
    assign_json = serialize('json', assignments)
    return HttpResponse(assign_json, mimetype='application/json')

def debits(request):
    debits = Debit.objects.all()
    debit_json = serialize('json', debits)
    return HttpResponse(debit_json, mimetype='application/json')

def credits(request):
    credits = Credit.objects.all()
    credit_json = serialize('json', credits)
    return HttpResponse(credit_json, mimetype='application/json')

