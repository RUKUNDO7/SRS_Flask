from datetime import datetime, timezone
from flask_login import UserMixin
from app import db


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Forward-reference helper used in ClassSection.enrolled_count
# ---------------------------------------------------------------------------
def _enrollment_count(section_id):
    return db.session.query(Enrollment).filter_by(
        class_section_id=section_id, status='enrolled'
    ).count()


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin | dos | accountant | student
    full_name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    is_active = db.Column(db.Boolean, default=True)
    session_token = db.Column(db.String(64), nullable=True)  # invalidated on server restart

    student_profile = db.relationship('Student', back_populates='user', uselist=False)

    def __repr__(self):
        return f'<User {self.username} [{self.role}]>'


class Term(db.Model):
    """School terms: Term 1, Term 2, Term 3."""
    __tablename__ = 'terms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False)        # e.g. "Term 1"
    academic_year = db.Column(db.String(20), nullable=False)  # e.g. "2024/2025"
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)

    def __repr__(self):
        return f'<Term {self.name} {self.academic_year}>'


class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(10), nullable=True)       # Male | Female | Other
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    guardian_name = db.Column(db.String(120), nullable=True)
    guardian_phone = db.Column(db.String(20), nullable=True)
    enrollment_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    status = db.Column(db.String(20), default='active')    # active | suspended | graduated
    year_group = db.Column(db.String(10), nullable=True)   # Year 1 | Year 2 | Year 3
    assigned_class = db.Column(db.String(5), nullable=True)  # A | B | C  (set by DOS)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=True)
    term = db.relationship('Term', backref='students')

    user = db.relationship('User', back_populates='student_profile')
    enrollments = db.relationship('Enrollment', back_populates='student', lazy='select')
    fee_records = db.relationship('FeeRecord', back_populates='student', lazy='select')

    def __repr__(self):
        return f'<Student {self.student_id}>'


class Course(db.Model):
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    credits = db.Column(db.Integer, default=3)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)

    class_sections = db.relationship('ClassSection', back_populates='course', lazy='select')

    def __repr__(self):
        return f'<Course {self.code}>'


class ClassSection(db.Model):
    __tablename__ = 'class_sections'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    section_name = db.Column(db.String(20), nullable=False)
    instructor = db.Column(db.String(120), nullable=True)
    schedule = db.Column(db.String(200), nullable=True)
    room = db.Column(db.String(50), nullable=True)
    semester = db.Column(db.String(30), nullable=False)
    max_students = db.Column(db.Integer, default=30)
    created_at = db.Column(db.DateTime(timezone=True), default=_now)

    course = db.relationship('Course', back_populates='class_sections')
    enrollments = db.relationship('Enrollment', back_populates='class_section', lazy='select')

    @property
    def enrolled_count(self):
        return _enrollment_count(self.id)

    def __repr__(self):
        return f'<ClassSection {self.section_name} [{self.course.code if self.course else "?"}]>'


class Enrollment(db.Model):
    __tablename__ = 'enrollments'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    class_section_id = db.Column(db.Integer, db.ForeignKey('class_sections.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime(timezone=True), default=_now)
    status = db.Column(db.String(20), default='enrolled')  # enrolled | dropped | completed

    student = db.relationship('Student', back_populates='enrollments')
    class_section = db.relationship('ClassSection', back_populates='enrollments')

    __table_args__ = (
        db.UniqueConstraint('student_id', 'class_section_id', name='uq_student_section'),
    )

    def __repr__(self):
        return f'<Enrollment student={self.student_id} section={self.class_section_id}>'


class FeeRecord(db.Model):
    __tablename__ = 'fee_records'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    fee_type = db.Column(db.String(50), nullable=False)
    semester = db.Column(db.String(30), nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    paid_amount = db.Column(db.Float, default=0.0)
    paid_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='pending')   # pending | partial | paid | overdue
    created_at = db.Column(db.DateTime(timezone=True), default=_now)

    student = db.relationship('Student', back_populates='fee_records')

    @property
    def balance(self):
        return self.amount - self.paid_amount

    def __repr__(self):
        return f'<FeeRecord student={self.student_id} amount={self.amount}>'
