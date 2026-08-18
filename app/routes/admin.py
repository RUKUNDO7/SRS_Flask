from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from werkzeug.security import generate_password_hash
from datetime import date, datetime
from app import db
from app.models import User, Student, Term, Enrollment, FeeRecord
from app.utils import role_required

admin_bp = Blueprint('admin', __name__)

YEAR_GROUPS = ['Year 1', 'Year 2', 'Year 3']
TERMS = ['Term 1', 'Term 2', 'Term 3']


def _sentence(value: str) -> str:
    """Title-case a string for consistent storage."""
    return ' '.join(w.capitalize() for w in value.split()) if value else value


def _get_active_term():
    return Term.query.filter_by(is_active=True).first()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@admin_bp.route('/dashboard')
@login_required
@role_required('admin')
def dashboard():
    active_term = _get_active_term()
    all_terms = Term.query.order_by(Term.academic_year.desc(), Term.id).all()

    # Stats scoped to active term if one exists, otherwise all-time
    base = Student.query.filter_by(term_id=active_term.id) if active_term else Student.query

    stats = {
        'total_students': base.count(),
        'active_students': base.filter_by(status='active').count(),
        'year1': base.filter_by(year_group='Year 1', status='active').count(),
        'year2': base.filter_by(year_group='Year 2', status='active').count(),
        'year3': base.filter_by(year_group='Year 3', status='active').count(),
    }

    recent_students = (
        Student.query.join(User)
        .filter(Student.term_id == active_term.id if active_term else True)
        .order_by(Student.enrollment_date.desc())
        .limit(6).all()
    )

    # Per-term student counts for the terms summary
    for t in all_terms:
        t.student_count = Student.query.filter_by(term_id=t.id).count()

    return render_template(
        'admin/dashboard.html',
        stats=stats,
        active_term=active_term,
        recent_students=recent_students,
        all_terms=all_terms,
    )


# ── Terms ─────────────────────────────────────────────────────────────────────

@admin_bp.route('/terms')
@login_required
@role_required('admin')
def terms():
    all_terms = Term.query.order_by(Term.academic_year.desc(), Term.id).all()
    for t in all_terms:
        t.student_count = Student.query.filter_by(term_id=t.id).count()
        t.year_counts = {
            'Year 1': Student.query.filter_by(term_id=t.id, year_group='Year 1').count(),
            'Year 2': Student.query.filter_by(term_id=t.id, year_group='Year 2').count(),
            'Year 3': Student.query.filter_by(term_id=t.id, year_group='Year 3').count(),
        }
    return render_template('admin/terms.html', terms=all_terms)


@admin_bp.route('/terms/new', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def new_term():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        academic_year = request.form.get('academic_year', '').strip()
        start_str = request.form.get('start_date', '')
        end_str = request.form.get('end_date', '')
        activate_now = request.form.get('activate_now') == '1'

        if not name or not academic_year:
            flash('Term name and academic year are required.', 'danger')
            return render_template('admin/term_form.html', terms=TERMS, form=request.form)

        start_date = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else None
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else None

        if activate_now:
            Term.query.update({'is_active': False})

        term = Term(
            name=name, academic_year=academic_year,
            start_date=start_date, end_date=end_date,
            is_active=activate_now,
        )
        db.session.add(term)
        db.session.commit()
        flash(
            f'{name} ({academic_year}) created'
            + (' and set as the active term.' if activate_now else '.'),
            'success',
        )
        return redirect(url_for('admin.terms'))

    return render_template('admin/term_form.html', terms=TERMS, form={})


@admin_bp.route('/terms/<int:term_id>/activate', methods=['POST'])
@login_required
@role_required('admin')
def activate_term(term_id):
    term = db.get_or_404(Term, term_id)
    Term.query.update({'is_active': False})
    term.is_active = True
    db.session.commit()
    flash(f'{term.name} ({term.academic_year}) is now the active term.', 'success')
    return redirect(url_for('admin.terms'))


@admin_bp.route('/terms/<int:term_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_term(term_id):
    term = db.get_or_404(Term, term_id)
    count = Student.query.filter_by(term_id=term.id).count()
    if count > 0:
        flash(
            f'Cannot delete — {count} student(s) are registered under this term. '
            'Move or remove those students first.',
            'danger',
        )
        return redirect(url_for('admin.terms'))
    db.session.delete(term)
    db.session.commit()
    flash('Term deleted.', 'success')
    return redirect(url_for('admin.terms'))


@admin_bp.route('/terms/<int:term_id>/students')
@login_required
@role_required('admin')
def term_students(term_id):
    """View all students enrolled in a specific term."""
    term = db.get_or_404(Term, term_id)
    students_list = (
        Student.query.join(User)
        .filter(Student.term_id == term_id)
        .order_by(Student.year_group, User.full_name)
        .all()
    )
    return render_template(
        'admin/term_students.html',
        term=term,
        students=students_list,
    )


# ── Students ──────────────────────────────────────────────────────────────────

@admin_bp.route('/students')
@login_required
@role_required('admin')
def students():
    active_term = _get_active_term()
    all_terms = Term.query.order_by(Term.academic_year.desc(), Term.id).all()

    # Default to active term filter; allow switching via query param
    term_id_filter = request.args.get('term_id', '')
    if term_id_filter == '':
        # Default: show active term if one exists, else show all
        selected_term = active_term
        term_id_filter = str(active_term.id) if active_term else ''
    else:
        selected_term = db.session.get(Term, int(term_id_filter)) if term_id_filter else None

    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')
    year_filter = request.args.get('year_group', '')

    query = Student.query.join(User)

    if term_id_filter:
        query = query.filter(Student.term_id == int(term_id_filter))

    if search:
        query = query.filter(db.or_(
            User.full_name.ilike(f'%{search}%'),
            Student.student_id.ilike(f'%{search}%'),
            User.email.ilike(f'%{search}%'),
        ))
    if status_filter:
        query = query.filter(Student.status == status_filter)
    if year_filter:
        query = query.filter(Student.year_group == year_filter)

    students_list = query.order_by(Student.year_group, Student.enrollment_date.desc()).all()

    return render_template(
        'admin/students.html',
        students=students_list,
        search=search,
        status_filter=status_filter,
        year_filter=year_filter,
        year_groups=YEAR_GROUPS,
        all_terms=all_terms,
        active_term=active_term,
        selected_term=selected_term,
        term_id_filter=term_id_filter,
    )


@admin_bp.route('/students/new', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def new_student():
    active_term = _get_active_term()
    all_terms = Term.query.order_by(Term.academic_year.desc(), Term.id).all()

    # Warn but don't block — admin can still pick a term from the form
    if not active_term and not all_terms:
        flash('No terms exist yet. Please create a term first.', 'danger')
        return redirect(url_for('admin.terms'))

    if request.method == 'POST':
        full_name = _sentence(request.form.get('full_name', '').strip())
        email = request.form.get('email', '').strip().lower()
        dob_str = request.form.get('date_of_birth', '')
        gender = request.form.get('gender', '')
        phone = request.form.get('phone', '').strip()
        address = _sentence(request.form.get('address', '').strip())
        guardian_name = _sentence(request.form.get('guardian_name', '').strip())
        guardian_phone = request.form.get('guardian_phone', '').strip()
        year_group = request.form.get('year_group', '')
        term_id_str = request.form.get('term_id', '')

        # Auto-generate username from name (e.g. "John Doe" → "john.doe")
        # and a default password equal to the student ID (set after flush)
        base_username = full_name.lower().replace(' ', '.')
        username = base_username
        suffix = 1
        while User.query.filter_by(username=username).first():
            username = f'{base_username}{suffix}'
            suffix += 1

        errors = []
        if not full_name:
            errors.append('Full name is required.')
        if not email:
            errors.append('Email is required.')
        if not year_group or year_group not in YEAR_GROUPS:
            errors.append('Please select a valid year group.')
        if not term_id_str:
            errors.append('Please select a term.')
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template(
                'admin/student_form.html', action='new',
                form=request.form, year_groups=YEAR_GROUPS,
                active_term=active_term, all_terms=all_terms,
                today=date.today().isoformat(),
                min_dob=date(date.today().year - 25, date.today().month, date.today().day).isoformat(),
            )

        selected_term = db.session.get(Term, int(term_id_str))

        # Collision-safe student ID
        yr = date.today().year
        count = Student.query.filter(Student.student_id.like(f'STU-{yr}-%')).count()
        student_id = f'STU-{yr}-{count + 1:04d}'
        while Student.query.filter_by(student_id=student_id).first():
            count += 1
            student_id = f'STU-{yr}-{count + 1:04d}'

        user = User(
            username=username, email=email, full_name=full_name,
            role='student', password_hash=generate_password_hash(student_id),
        )
        db.session.add(user)
        db.session.flush()

        dob = None
        if dob_str:
            try:
                dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
                today_date = date.today()
                age = (today_date - dob).days // 365
                if dob > today_date:
                    errors.append('Date of birth cannot be in the future.')
                    dob = None
                elif age < 5:
                    errors.append('Student must be at least 5 years old.')
                    dob = None
                elif age > 25:
                    errors.append('Student must be 25 years old or younger.')
                    dob = None
            except ValueError:
                errors.append('Invalid date of birth format.')

        student = Student(
            user_id=user.id,
            student_id=student_id,
            date_of_birth=dob,
            gender=gender,
            phone=phone,
            address=address,
            guardian_name=guardian_name,
            guardian_phone=guardian_phone,
            enrollment_date=date.today(),
            year_group=year_group,
            term_id=selected_term.id,
        )
        db.session.add(student)
        db.session.flush()   # get student.id before committing

        # ── Auto-create fee record from registration form ──────────────
        SCHOOL_FEE_TOTAL = 85000.0
        fee_status_input = request.form.get('fee_status', 'pending')

        if fee_status_input == 'paid':
            fee_paid   = SCHOOL_FEE_TOTAL
            fee_status = 'paid'
        elif fee_status_input in ('partial', 'overdue'):
            try:
                remaining  = float(request.form.get('fee_remaining', '0') or 0)
                remaining  = max(0.0, min(remaining, SCHOOL_FEE_TOTAL))
                fee_paid   = SCHOOL_FEE_TOTAL - remaining
                fee_status = fee_status_input
            except ValueError:
                fee_paid   = 0.0
                fee_status = fee_status_input
        else:
            # pending
            fee_paid   = 0.0
            fee_status = 'pending'

        fee_record = FeeRecord(
            student_id=student.id,
            description=f'School Fees — {selected_term.name} {selected_term.academic_year}',
            amount=SCHOOL_FEE_TOTAL,
            fee_type='tuition',
            semester=f'{selected_term.name} {selected_term.academic_year}',
            paid_amount=fee_paid,
            paid_date=date.today() if fee_paid > 0 else None,
            status=fee_status,
        )
        db.session.add(fee_record)

        db.session.commit()
        flash(
            f'{full_name} registered as {student_id} ({year_group}) '
            f'under {selected_term.name} {selected_term.academic_year}.',
            'success',
        )
        # Stay on the registration form so the admin can keep adding students.
        # Pass the last registered student's info for the success notice.
        return redirect(url_for('admin.new_student', registered=student_id, name=full_name))

    return render_template(
        'admin/student_form.html', action='new',
        form={}, year_groups=YEAR_GROUPS,
        active_term=active_term, all_terms=all_terms,
        today=date.today().isoformat(),
        min_dob=date(date.today().year - 25, date.today().month, date.today().day).isoformat(),
    )


@admin_bp.route('/students/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit_student(student_id):
    student = db.get_or_404(Student, student_id)
    user = student.user
    all_terms = Term.query.order_by(Term.academic_year.desc(), Term.id).all()

    if request.method == 'POST':
        user.full_name = _sentence(request.form.get('full_name', user.full_name).strip())
        user.email = request.form.get('email', user.email).strip().lower()
        student.gender = request.form.get('gender', '')
        student.phone = request.form.get('phone', '').strip()
        student.address = _sentence(request.form.get('address', '').strip())
        student.guardian_name = _sentence(request.form.get('guardian_name', '').strip())
        student.guardian_phone = request.form.get('guardian_phone', '').strip()
        student.status = request.form.get('status', student.status)
        student.year_group = request.form.get('year_group', student.year_group)

        term_id_val = request.form.get('term_id', '')
        student.term_id = int(term_id_val) if term_id_val else student.term_id

        dob_str = request.form.get('date_of_birth', '')
        if dob_str:
            try:
                student.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        new_password = request.form.get('new_password', '').strip()
        if new_password:
            user.password_hash = generate_password_hash(new_password)

        db.session.commit()
        flash('Student record updated.', 'success')
        return redirect(url_for('admin.students'))

    return render_template(
        'admin/student_form.html', action='edit',
        student=student, form={}, year_groups=YEAR_GROUPS,
        all_terms=all_terms, active_term=_get_active_term(),
        today=date.today().isoformat(),
        min_dob=date(date.today().year - 25, date.today().month, date.today().day).isoformat(),
    )


@admin_bp.route('/students/<int:student_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_student(student_id):
    student = db.get_or_404(Student, student_id)
    user = student.user
    Enrollment.query.filter_by(student_id=student.id).delete()
    FeeRecord.query.filter_by(student_id=student.id).delete()
    db.session.delete(student)
    db.session.delete(user)
    db.session.commit()
    flash('Student record deleted.', 'success')
    return redirect(url_for('admin.students'))
