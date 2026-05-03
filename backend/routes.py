import re
from flask import current_app, render_template, jsonify, request, url_for
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash
from Test1.backend.models import Admin, Opportunity, db

CATEGORY_LABELS = {
    'technology': 'Technology',
    'business': 'Business',
    'design': 'Design',
    'marketing': 'Marketing',
    'data': 'Data Science',
    'other': 'Other'
}

EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

def init_routes(app, login_manager):
    @login_manager.unauthorized_handler
    def unauthorized():
        return jsonify({'error': 'Authentication required'}), 401

    @app.route('/')
    def index():
        return render_template('admin.html')

    @app.route('/api/current-user')
    def current_user_info():
        if current_user.is_authenticated:
            return jsonify({'authenticated': True, 'email': current_user.email, 'full_name': current_user.full_name}), 200
        return jsonify({'authenticated': False}), 200

    @app.route('/api/signup', methods=['POST'])
    def signup():
        data = request.get_json() or {}
        full_name = (data.get('fullName') or '').strip()
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''
        confirm_password = data.get('confirmPassword') or ''

        if not full_name or not email or not password or not confirm_password:
            return jsonify({'error': 'All fields are required'}), 400
        if not EMAIL_REGEX.match(email):
            return jsonify({'error': 'Invalid email format'}), 400
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        if password != confirm_password:
            return jsonify({'error': 'Passwords must match'}), 400
        if Admin.query.filter_by(email=email).first():
            return jsonify({'error': 'Account already exists'}), 400

        admin = Admin(
            full_name=full_name,
            email=email,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256')
        )
        db.session.add(admin)
        db.session.commit()
        return jsonify({'status': 'success'}), 201

    @app.route('/api/login', methods=['POST'])
    def login():
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''
        remember = bool(data.get('remember'))

        if not email or not password:
            return jsonify({'error': 'Invalid email or password'}), 401

        user = Admin.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({'error': 'Invalid email or password'}), 401

        login_user(user, remember=remember)
        return jsonify({'status': 'success'}), 200

    @app.route('/api/logout', methods=['POST'])
    @login_required
    def logout():
        logout_user()
        return jsonify({'status': 'success'}), 200

    @app.route('/api/forgot-password', methods=['POST'])
    def forgot_password():
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        admin = Admin.query.filter_by(email=email).first() if email else None
        if admin:
            serializer = get_serializer()
            token = serializer.dumps(email, salt='password-reset-salt')
            reset_url = url_for('reset_password', token=token, _external=True)
            current_app.logger.info('Password reset link for %s: %s', email, reset_url)
        return jsonify({'status': 'success'}), 200

    @app.route('/reset-password/<token>')
    def reset_password(token):
        serializer = get_serializer()
        try:
            email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
        except SignatureExpired:
            return '<h1>Reset link expired</h1><p>This password reset link has expired. Please request a new one.</p>', 400
        except (BadSignature, Exception):
            return '<h1>Invalid reset link</h1><p>The password reset link is invalid.</p>', 400

        return '<h1>Reset link valid</h1><p>This token is valid for email: {}</p>'.format(email), 200

    def get_opportunity_or_404(opp_id):
        opportunity = Opportunity.query.filter_by(id=opp_id, admin_id=current_user.id).first()
        if not opportunity:
            return None
        return opportunity

    @app.route('/api/opportunities', methods=['GET'])
    @login_required
    def get_opportunities():
        opportunities = Opportunity.query.filter_by(admin_id=current_user.id).order_by(Opportunity.created_at.desc()).all()
        return jsonify({'status': 'success', 'opportunities': [opp.to_dict() for opp in opportunities]}), 200

    @app.route('/api/opportunities', methods=['POST'])
    @login_required
    def create_opportunity():
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        duration = (data.get('duration') or '').strip()
        start_date = (data.get('startDate') or '').strip()
        description = (data.get('description') or '').strip()
        skills = data.get('skills') or []
        category = (data.get('category') or '').strip()
        future_opportunities = (data.get('futureOpportunities') or '').strip()
        max_applicants = data.get('maxApplicants')

        if not name or not duration or not start_date or not description or not skills or not category or not future_opportunities:
            return jsonify({'error': 'All required fields must be filled'}), 400
        if category not in CATEGORY_LABELS.values():
            return jsonify({'error': 'Invalid category'}), 400
        if not isinstance(skills, list) or len([s for s in skills if s.strip()]) == 0:
            return jsonify({'error': 'Skills must be a non-empty list'}), 400
        if max_applicants is not None:
            try:
                max_applicants = int(max_applicants)
                if max_applicants < 0:
                    raise ValueError
            except (ValueError, TypeError):
                return jsonify({'error': 'Maximum applicants must be a positive number'}), 400

        opportunity = Opportunity(
            name=name,
            duration=duration,
            start_date=start_date,
            description=description,
            skills=','.join([skill.strip() for skill in skills if skill.strip()]),
            category=category,
            future_opportunities=future_opportunities,
            max_applicants=max_applicants,
            admin_id=current_user.id
        )
        db.session.add(opportunity)
        db.session.commit()
        return jsonify({'status': 'success', 'opportunity': opportunity.to_dict()}), 201

    @app.route('/api/opportunities/<int:opp_id>', methods=['GET'])
    @login_required
    def get_opportunity(opp_id):
        opportunity = get_opportunity_or_404(opp_id)
        if not opportunity:
            return jsonify({'error': 'Opportunity not found'}), 404
        return jsonify({'status': 'success', 'opportunity': opportunity.to_dict()}), 200

    @app.route('/api/opportunities/<int:opp_id>', methods=['PUT'])
    @login_required
    def update_opportunity(opp_id):
        opportunity = get_opportunity_or_404(opp_id)
        if not opportunity:
            return jsonify({'error': 'Opportunity not found'}), 404

        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        duration = (data.get('duration') or '').strip()
        start_date = (data.get('startDate') or '').strip()
        description = (data.get('description') or '').strip()
        skills = data.get('skills') or []
        category = (data.get('category') or '').strip()
        future_opportunities = (data.get('futureOpportunities') or '').strip()
        max_applicants = data.get('maxApplicants')

        if not name or not duration or not start_date or not description or not skills or not category or not future_opportunities:
            return jsonify({'error': 'All required fields must be filled'}), 400
        if category not in CATEGORY_LABELS.values():
            return jsonify({'error': 'Invalid category'}), 400
        if not isinstance(skills, list) or len([s for s in skills if s.strip()]) == 0:
            return jsonify({'error': 'Skills must be a non-empty list'}), 400
        if max_applicants is not None:
            try:
                max_applicants = int(max_applicants)
                if max_applicants < 0:
                    raise ValueError
            except (ValueError, TypeError):
                return jsonify({'error': 'Maximum applicants must be a positive number'}), 400

        opportunity.name = name
        opportunity.duration = duration
        opportunity.start_date = start_date
        opportunity.description = description
        opportunity.skills = ','.join([skill.strip() for skill in skills if skill.strip()])
        opportunity.category = category
        opportunity.future_opportunities = future_opportunities
        opportunity.max_applicants = max_applicants

        db.session.commit()
        return jsonify({'status': 'success', 'opportunity': opportunity.to_dict()}), 200

    @app.route('/api/opportunities/<int:opp_id>', methods=['DELETE'])
    @login_required
    def delete_opportunity(opp_id):
        opportunity = get_opportunity_or_404(opp_id)
        if not opportunity:
            return jsonify({'error': 'Opportunity not found'}), 404
        db.session.delete(opportunity)
        db.session.commit()
        return jsonify({'status': 'success'}), 200
