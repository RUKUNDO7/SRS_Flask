from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import Student, Enrollment, FeeRecord, Course, ClassSection
from app.utils import role_required

student_bp = Blueprint('student', __name__)


@student_bp.route('/dashboard')
@login_required
@role_required('student')
def dashboard():
    student = current_user.student_profile
    if not student:
        return render_template('student/no_profile.html')

    enrollments = (
        Enrollment.query
        .filter_by(student_id=student.id, status='enrolled')
        .join(ClassSection)
        .join(Course)
        .order_by(Course.code)
        .all()
    )
    pending_fees = FeeRecord.query.filter(
        FeeRecord.student_id == student.id,
        FeeRecord.status.in_(['pending', 'partial', 'overdue'])
    ).all()
    total_outstanding = sum(r.balance for r in pending_fees)

    return render_template(
        'student/dashboard.html',
        student=student,
        enrollments=enrollments,
        pending_fees=pending_fees,
        total_outstanding=total_outstanding,
    )


@student_bp.route('/classes')
@login_required
@role_required('student')
def classes():
    student = current_user.student_profile
    enrollments = (
        Enrollment.query
        .filter_by(student_id=student.id, status='enrolled')
        .join(ClassSection)
        .join(Course)
        .order_by(Course.code)
        .all()
    )
    return render_template('student/classes.html', student=student, enrollments=enrollments)


@student_bp.route('/fees')
@login_required
@role_required('student')
def fees():
    student = current_user.student_profile
    records = FeeRecord.query.filter_by(student_id=student.id).order_by(FeeRecord.created_at.desc()).all()
    total_billed = sum(r.amount for r in records)
    total_paid = sum(r.paid_amount for r in records)
    balance = total_billed - total_paid
    return render_template(
        'student/fees.html',
        student=student,
        records=records,
        total_billed=total_billed,
        total_paid=total_paid,
        balance=balance,
    )


@student_bp.route('/profile')
@login_required
@role_required('student')
def profile():
    student = current_user.student_profile
    return render_template('student/profile.html', student=student)
