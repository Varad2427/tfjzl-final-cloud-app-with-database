
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from .models import Course, Enrollment, Question, Choice, Submission
import logging

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}

    if request.method == 'GET':
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)

    elif request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']

        user_exist = False

        try:
            User.objects.get(username=username)
            user_exist = True
        except User.DoesNotExist:
            logger.info("New user registration")

        if not user_exist:
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password
            )
            login(request, user)
            return redirect("onlinecourse:index")

        context['message'] = "User already exists."
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)


def login_request(request):
    context = {}

    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']

        user = authenticate(username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = "Invalid username or password."
        return render(request, 'onlinecourse/user_login_bootstrap.html', context)

    return render(request, 'onlinecourse/user_login_bootstrap.html', context)


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    if user.is_authenticated:
        return Enrollment.objects.filter(user=user, course=course).exists()
    return False


class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]

        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)

        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    is_enrolled = check_if_enrolled(user, course)

    if not is_enrolled and user.is_authenticated:
        Enrollment.objects.create(user=user, course=course, mode='honor')
        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(
        reverse('onlinecourse:course_details', args=(course.id,))
    )


def extract_answers(request):
    submitted_answers = []

    for key in request.POST:
        if key.startswith('choice'):
            try:
                choice_id = int(request.POST[key])
                submitted_answers.append(choice_id)
            except (ValueError, TypeError):
                continue

    return submitted_answers


@login_required
@require_POST
def submit(request, course_id):
    course = get_object_or_404(Course, pk=course_id)

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    submission = Submission.objects.create(enrollment=enrollment)

    submitted_answers = extract_answers(request)

    choices = Choice.objects.filter(
        id__in=submitted_answers,
        question__course=course
    )

    submission.choices.set(choices)

    return HttpResponseRedirect(
        reverse(
            'onlinecourse:show_exam_result',
            args=(course.id, submission.id)
        )
    )


@login_required
def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__user=request.user,
        enrollment__course=course
    )

    questions = Question.objects.filter(course=course)
    selected_choices = submission.choices.all()

    total_score = 0
    question_results = []

    for question in questions:
        selected_for_question = selected_choices.filter(question=question)

        selected_ids = list(
            selected_for_question.values_list('id', flat=True)
        )

        is_correct = question.is_get_score(selected_ids)

        question_score = question.grade if is_correct else 0
        total_score += question_score

        question_results.append({
            'question': question,
            'selected_choices': selected_for_question,
            'is_correct': is_correct,
            'score': question_score
        })

    maximum_score = sum(question.grade for question in questions)

    passed = (
        maximum_score > 0 and total_score >= maximum_score * 0.8
    )

    context = {
        'course': course,
        'submission': submission,
        'question_results': question_results,
        'total_score': total_score,
        'maximum_score': maximum_score,
        'passed': passed
    }

    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context
    )
