import random
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app import db
from app.models import Student, ClassSection, Enrollment, User
from app.utils import role_required

dos_bp = Blueprint('dos', __name__)

CLASSES = ['A', 'B', 'C']
YEAR_GROUPS = ['Year 1', 'Year 2', 'Year 3']


# ── Dashboard ─────────────────────────────────────────────────────────────────

@dos_bp.route('/dashboard')
@login_required
@role_required('dos')
def dashboard():
    stats = {
        'total_sections': ClassSection.query.count(),
        'total_enrollments': Enrollment.query.filter_by(status='enrolled').count(),
        'total_students': Student.query.filter_by(status='active').count(),
        'unassigned': Student.query.filter_by(status='active', assigned_class=None).count(),
    }
    recent_sections = ClassSection.query.order_by(ClassSection.id.desc()).limit(6).all()
    unassigned_students = (
        Student.query.join(User)
        .filter(Student.status == 'active', Student.assigned_class.is_(None))
        .order_by(Student.year_group, User.full_name)
        .limit(8).all()
    )
    return render_template('dos/dashboard.html', stats=stats,
                           sections=recent_sections,
                           unassigned_students=unassigned_students)


# ── Class assignment ──────────────────────────────────────────────────────────

@dos_bp.route('/assign-classes', methods=['GET', 'POST'])
@login_required
@role_required('dos')
def assign_classes():
    """
    Auto-assign classes A/B/C per year group.
    Males and females are distributed as evenly as possible across the three classes.
    Students who already have an assigned_class are left untouched unless 'reassign' is checked.
    """
    year_filter = request.args.get('year_group', '')

    if request.method == 'POST':
        year_group = request.form.get('year_group', '')
        reassign = request.form.get('reassign') == '1'

        if year_group not in YEAR_GROUPS:
            flash('Invalid year group.', 'danger')
            return redirect(url_for('dos.assign_classes'))

        query = Student.query.join(User).filter(
            Student.status == 'active',
            Student.year_group == year_group,
        )
        if not reassign:
            query = query.filter(Student.assigned_class.is_(None))

        students = query.order_by(User.full_name).all()

        if not students:
            flash('No eligible students found for that year group.', 'warning')
            return redirect(url_for('dos.assign_classes'))

        # Separate by gender, shuffle each group for randomness
        males = [s for s in students if s.gender == 'Male']
        females = [s for s in students if s.gender == 'Female']
        others = [s for s in students if s.gender not in ('Male', 'Female')]

        random.shuffle(males)
        random.shuffle(females)
        random.shuffle(others)

        # Round-robin across A, B, C — interleave genders so each class
        # gets roughly equal males and females
        interleaved = []
        max_len = max(len(males), len(females), len(others))
        for i in range(max_len):
            if i < len(males):
                interleaved.append(males[i])
            if i < len(females):
                interleaved.append(females[i])
            if i < len(others):
                interleaved.append(others[i])

        for idx, student in enumerate(interleaved):
            student.assigned_class = CLASSES[idx % 3]

        db.session.commit()
        flash(
            f'Assigned {len(interleaved)} students in {year_group} to classes '
            f'A/B/C with gender balancing.',
            'success',
        )
        return redirect(url_for('dos.assign_classes'))

    # GET — show summary per year group
    summaries = []
    for yg in YEAR_GROUPS:
        row = {'year_group': yg, 'classes': {}}
        for cls in CLASSES:
            count = Student.query.filter_by(
                year_group=yg, assigned_class=cls, status='active'
            ).count()
            row['classes'][cls] = count
        row['unassigned'] = Student.query.filter_by(
            year_group=yg, status='active', assigned_class=None
        ).count()
        summaries.append(row)

    # Detailed list
    query = Student.query.join(User).filter(Student.status == 'active')
    if year_filter:
        query = query.filter(Student.year_group == year_filter)
    students_list = query.order_by(Student.year_group, Student.assigned_class, User.full_name).all()

    return render_template(
        'dos/assign_classes.html',
        summaries=summaries,
        students_list=students_list,
        year_groups=YEAR_GROUPS,
        classes=CLASSES,
        year_filter=year_filter,
    )


# ── Class Sections ────────────────────────────────────────────────────────────

@dos_bp.route('/sections')
@login_required
@role_required('dos')
def sections():
    semester_filter = request.args.get('semester', '')
    query = ClassSection.query
    if semester_filter:
        query = query.filter(ClassSection.semester == semester_filter)
    sections_list = query.order_by(ClassSection.section_name).all()
    semesters = [s[0] for s in db.session.query(ClassSection.semester).distinct().all()]
    return render_template(
        'dos/sections.html',
        sections=sections_list, semesters=semesters,
        semester_filter=semester_filter,
    )


@dos_bp.route('/sections/new', methods=['GET', 'POST'])
@login_required
@role_required('dos')
def new_section():
    if request.method == 'POST':
        section_name = request.form.get('section_name', '').strip()
        instructor = request.form.get('instructor', '').strip()
        schedule = request.form.get('schedule', '').strip()
        room = request.form.get('room', '').strip()
        semester = request.form.get('semester', '').strip()
        max_students = int(request.form.get('max_students', 30))

        if not section_name or not semester:
            flash('Section name and semester are required.', 'danger')
            return render_template('dos/section_form.html', action='new', form=request.form)

        section = ClassSection(
            course_id=1,  # placeholder — courses removed for now
            section_name=section_name,
            instructor=instructor, schedule=schedule,
            room=room, semester=semester, max_students=max_students,
        )
        db.session.add(section)
        db.session.commit()
        flash(f'Section "{section_name}" created.', 'success')
        return redirect(url_for('dos.sections'))

    return render_template('dos/section_form.html', action='new', form={})


@dos_bp.route('/sections/<int:section_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('dos')
def edit_section(section_id):
    section = db.get_or_404(ClassSection, section_id)
    courses = Course.query.order_by(Course.code).all()
    if request.method == 'POST':
        section.course_id = int(request.form.get('course_id', section.course_id))
        section.section_name = request.form.get('section_name', section.section_name).strip()
        section.instructor = request.form.get('instructor', '').strip()
        section.schedule = request.form.get('schedule', '').strip()
        section.room = request.form.get('room', '').strip()
        section.semester = request.form.get('semester', section.semester).strip()
        section.max_students = int(request.form.get('max_students', section.max_students))
        db.session.commit()
        flash('Section updated.', 'success')
        return redirect(url_for('dos.sections'))
    return render_template('dos/section_form.html', action='edit',
                           section=section, courses=courses, form={})


@dos_bp.route('/sections/<int:section_id>/delete', methods=['POST'])
@login_required
@role_required('dos')
def delete_section(section_id):
    section = db.get_or_404(ClassSection, section_id)
    Enrollment.query.filter_by(class_section_id=section_id).delete()
    db.session.delete(section)
    db.session.commit()
    flash('Section deleted.', 'success')
    return redirect(url_for('dos.sections'))


# ── Enrollments ───────────────────────────────────────────────────────────────

@dos_bp.route('/sections/<int:section_id>/enrollments')
@login_required
@role_required('dos')
def section_enrollments(section_id):
    section = db.get_or_404(ClassSection, section_id)
    enrolled = (
        Enrollment.query
        .filter_by(class_section_id=section_id, status='enrolled')
        .join(Student).join(User, Student.user_id == User.id)
        .order_by(User.full_name).all()
    )
    enrolled_ids = [e.student_id for e in enrolled]
    avail_q = (Student.query.join(User)
               .filter(Student.status == 'active')
               .order_by(User.full_name))
    if enrolled_ids:
        avail_q = avail_q.filter(~Student.id.in_(enrolled_ids))
    available_students = avail_q.all()
    return render_template('dos/enrollments.html', section=section,
                           enrolled=enrolled, available_students=available_students)


@dos_bp.route('/sections/<int:section_id>/enroll', methods=['POST'])
@login_required
@role_required('dos')
def enroll_student(section_id):
    section = db.get_or_404(ClassSection, section_id)
    student_id = int(request.form.get('student_id', 0))
    student = db.get_or_404(Student, student_id)

    if section.enrolled_count >= section.max_students:
        flash('Section is full.', 'danger')
        return redirect(url_for('dos.section_enrollments', section_id=section_id))

    existing = Enrollment.query.filter_by(
        student_id=student_id, class_section_id=section_id).first()
    if existing:
        if existing.status == 'enrolled':
            flash('Student is already enrolled.', 'warning')
        else:
            existing.status = 'enrolled'
            db.session.commit()
            flash('Student re-enrolled.', 'success')
    else:
        db.session.add(Enrollment(student_id=student_id, class_section_id=section_id))
        db.session.commit()
        flash(f'{student.user.full_name} enrolled in {section.section_name}.', 'success')
    return redirect(url_for('dos.section_enrollments', section_id=section_id))


@dos_bp.route('/enrollments/<int:enrollment_id>/drop', methods=['POST'])
@login_required
@role_required('dos')
def drop_enrollment(enrollment_id):
    enrollment = db.get_or_404(Enrollment, enrollment_id)
    section_id = enrollment.class_section_id
    enrollment.status = 'dropped'
    db.session.commit()
    flash('Student dropped from section.', 'success')
    return redirect(url_for('dos.section_enrollments', section_id=section_id))


# ── Students view ─────────────────────────────────────────────────────────────

@dos_bp.route('/students')
@login_required
@role_required('dos')
def students():
    year_filter = request.args.get('year_group', '')
    class_filter = request.args.get('assigned_class', '')
    query = Student.query.join(User).filter(Student.status == 'active')
    if year_filter:
        query = query.filter(Student.year_group == year_filter)
    if class_filter:
        query = query.filter(Student.assigned_class == class_filter)
    students_list = query.order_by(Student.year_group, Student.assigned_class, User.full_name).all()
    return render_template('dos/students.html', students=students_list,
                           year_groups=YEAR_GROUPS, classes=CLASSES,
                           year_filter=year_filter, class_filter=class_filter)


@dos_bp.route('/students/<int:student_id>/schedule')
@login_required
@role_required('dos')
def student_schedule(student_id):
    student = db.get_or_404(Student, student_id)
    enrollments = (
        Enrollment.query
        .filter_by(student_id=student_id, status='enrolled')
        .join(ClassSection).join(Course)
        .order_by(Course.code).all()
    )
    return render_template('dos/student_schedule.html', student=student, enrollments=enrollments)
