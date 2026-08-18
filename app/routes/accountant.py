from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from datetime import date, datetime
from app import db
from app.models import Student, FeeRecord, User
from app.utils import role_required

accountant_bp = Blueprint('accountant', __name__)


@accountant_bp.route('/dashboard')
@login_required
@role_required('accountant')
def dashboard():
    total_billed = db.session.query(db.func.sum(FeeRecord.amount)).scalar() or 0
    total_paid = db.session.query(db.func.sum(FeeRecord.paid_amount)).scalar() or 0
    total_outstanding = total_billed - total_paid
    pending_count = FeeRecord.query.filter(FeeRecord.status.in_(['pending', 'partial', 'overdue'])).count()

    recent_records = (
        FeeRecord.query
        .join(Student)
        .join(User, Student.user_id == User.id)
        .order_by(FeeRecord.created_at.desc())
        .limit(8)
        .all()
    )

    # ── Breakdown by Year Group and Class ─────────────────────────────
    year_class_breakdown = []
    for year in ['Year 1', 'Year 2', 'Year 3']:
        row = {'year': year, 'classes': []}
        year_total_b = 0
        year_total_p = 0
        for cls in ['A', 'B', 'C', None]:
            # None = unassigned
            students_q = Student.query.filter_by(year_group=year, assigned_class=cls)
            student_ids = [s.id for s in students_q.all()]
            if not student_ids:
                continue
            billed = db.session.query(db.func.sum(FeeRecord.amount))\
                .filter(FeeRecord.student_id.in_(student_ids)).scalar() or 0
            paid = db.session.query(db.func.sum(FeeRecord.paid_amount))\
                .filter(FeeRecord.student_id.in_(student_ids)).scalar() or 0
            year_total_b += billed
            year_total_p += paid
            row['classes'].append({
                'label': f'Class {cls}' if cls else 'Unassigned',
                'count': len(student_ids),
                'billed': billed,
                'paid': paid,
                'balance': billed - paid,
            })
        row['total_billed'] = year_total_b
        row['total_paid'] = year_total_p
        row['total_balance'] = year_total_b - year_total_p
        if row['classes']:
            year_class_breakdown.append(row)

    return render_template(
        'accountant/dashboard.html',
        total_billed=total_billed,
        total_paid=total_paid,
        total_outstanding=total_outstanding,
        pending_count=pending_count,
        recent_records=recent_records,
        year_class_breakdown=year_class_breakdown,
    )


# ── Fee Records ───────────────────────────────────────────────────────────────

@accountant_bp.route('/fees')
@login_required
@role_required('accountant')
def fees():
    status_filter   = request.args.get('status', '')
    semester_filter = request.args.get('semester', '')
    year_filter     = request.args.get('year_group', '')
    class_filter    = request.args.get('assigned_class', '')
    search          = request.args.get('search', '').strip()
    sort_by         = request.args.get('sort', 'created_at')
    sort_dir        = request.args.get('dir', 'desc')
    page            = request.args.get('page', 1, type=int)
    per_page        = 15

    query = FeeRecord.query.join(Student).join(User, Student.user_id == User.id)

    if status_filter:
        query = query.filter(FeeRecord.status == status_filter)
    if semester_filter:
        query = query.filter(FeeRecord.semester == semester_filter)
    if year_filter:
        query = query.filter(Student.year_group == year_filter)
    if class_filter:
        query = query.filter(Student.assigned_class == class_filter)
    if search:
        query = query.filter(db.or_(
            User.full_name.ilike(f'%{search}%'),
            Student.student_id.ilike(f'%{search}%'),
        ))

    # Sorting
    sort_map = {
        'name':       User.full_name,
        'amount':     FeeRecord.amount,
        'paid':       FeeRecord.paid_amount,
        'balance':    (FeeRecord.amount - FeeRecord.paid_amount),
        'status':     FeeRecord.status,
        'created_at': FeeRecord.created_at,
    }
    sort_col = sort_map.get(sort_by, FeeRecord.created_at)
    query = query.order_by(sort_col.desc() if sort_dir == 'desc' else sort_col.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    records    = pagination.items
    semesters  = [s[0] for s in db.session.query(FeeRecord.semester).distinct().all()]

    # Totals for the whole filtered set (not just current page)
    all_records = query.all()
    filter_total_billed = sum(r.amount for r in all_records)
    filter_total_paid   = sum(r.paid_amount for r in all_records)

    return render_template(
        'accountant/fees.html',
        records=records,
        pagination=pagination,
        semesters=semesters,
        status_filter=status_filter,
        semester_filter=semester_filter,
        year_filter=year_filter,
        class_filter=class_filter,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filter_total_billed=filter_total_billed,
        filter_total_paid=filter_total_paid,
    )


@accountant_bp.route('/fees/new', methods=['GET', 'POST'])
@login_required
@role_required('accountant')
def new_fee():
    students = Student.query.join(User).filter(Student.status == 'active').order_by(User.full_name).all()
    if request.method == 'POST':
        student_id = int(request.form.get('student_id', 0))
        description = request.form.get('description', '').strip()
        amount = float(request.form.get('amount', 0))
        fee_type = request.form.get('fee_type', 'tuition')
        semester = request.form.get('semester', '').strip()
        due_date_str = request.form.get('due_date', '')

        if not student_id or not description or not amount or not semester:
            flash('All required fields must be filled.', 'danger')
            return render_template('accountant/fee_form.html', action='new', students=students, form=request.form)

        due_date = None
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        record = FeeRecord(
            student_id=student_id,
            description=description,
            amount=amount,
            fee_type=fee_type,
            semester=semester,
            due_date=due_date,
        )
        db.session.add(record)
        db.session.commit()
        flash('Fee record created.', 'success')
        return redirect(url_for('accountant.fees'))

    return render_template('accountant/fee_form.html', action='new', students=students, form={})


@accountant_bp.route('/fees/<int:record_id>/payment', methods=['GET', 'POST'])
@login_required
@role_required('accountant')
def record_payment(record_id):
    record = db.get_or_404(FeeRecord, record_id)
    if request.method == 'POST':
        payment = float(request.form.get('payment_amount', 0))
        if payment <= 0:
            flash('Payment amount must be positive.', 'danger')
            return render_template('accountant/payment_form.html', record=record)
        if payment > record.balance:
            payment = record.balance

        record.paid_amount += payment
        record.paid_date = date.today()
        if record.paid_amount >= record.amount:
            record.status = 'paid'
        else:
            record.status = 'partial'
        db.session.commit()
        flash(f'Payment of ${payment:,.2f} recorded.', 'success')
        return redirect(url_for('accountant.fees'))

    return render_template('accountant/payment_form.html', record=record)


@accountant_bp.route('/fees/<int:record_id>/delete', methods=['POST'])
@login_required
@role_required('accountant')
def delete_fee(record_id):
    record = db.get_or_404(FeeRecord, record_id)
    db.session.delete(record)
    db.session.commit()
    flash('Fee record deleted.', 'success')
    return redirect(url_for('accountant.fees'))


# ── Per-student financial view ────────────────────────────────────────────────

@accountant_bp.route('/students')
@login_required
@role_required('accountant')
def students():
    students_list = (
        Student.query.join(User)
        .filter(Student.status == 'active')
        .order_by(User.full_name)
        .all()
    )
    # Build per-student financial summary
    summaries = []
    for s in students_list:
        records = FeeRecord.query.filter_by(student_id=s.id).all()
        total_b = sum(r.amount for r in records)
        total_p = sum(r.paid_amount for r in records)
        summaries.append({
            'student': s,
            'total_billed': total_b,
            'total_paid': total_p,
            'balance': total_b - total_p,
        })
    return render_template('accountant/students.html', summaries=summaries)


@accountant_bp.route('/students/<int:student_id>')
@login_required
@role_required('accountant')
def student_fees(student_id):
    student = db.get_or_404(Student, student_id)
    records = FeeRecord.query.filter_by(student_id=student_id).order_by(FeeRecord.created_at.desc()).all()
    total_billed = sum(r.amount for r in records)
    total_paid = sum(r.paid_amount for r in records)
    balance = total_billed - total_paid
    return render_template(
        'accountant/student_fees.html',
        student=student,
        records=records,
        total_billed=total_billed,
        total_paid=total_paid,
        balance=balance,
    )
