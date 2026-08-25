from importlib.resources import files

from flask import app, render_template, redirect, request, url_for, flash, session
from yaml import load_all
from vim_database.models import User, Vendor, ValidationResult
from vim_database.models import SystemConfiguration
from vim_database.database import db
from functools import wraps


def register_routes(app):

    # ---------------- AUTH HELPERS ----------------
    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if 'user_id' not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for('login'))
            return view(*args, **kwargs)
        return wrapped

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get('role') != 'admin':
                flash("Admin access required.", "danger")
                return redirect(url_for('login'))
            return view(*args, **kwargs)
        return wrapped

    # ---------------- HOME ROUTE ----------------
    @app.route('/')
    def home():
        return render_template('home.html')

    # ---------------- USER HOME (post-login) ----------------
    @app.route('/home/<int:user_id>')
    @login_required
    def user_home(user_id):
        if session['user_id'] != user_id:
            flash("You don't have access to that page.", "danger")
            return redirect(url_for('user_home', user_id=session['user_id']))
        return render_template('home.html', user_id=user_id)

    # ---------------- LOGIN ----------------
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form.get('email')
            password = request.form.get('password')

            this_user = User.query.filter_by(Email=email).first()

            if this_user:
                if this_user.PasswordHash == password:
                    session['user_id'] = this_user.UserID
                    session['role'] = this_user.Role
                    flash(f"Welcome back, {this_user.Username}!", "success")
                    if this_user.Role == 'admin':
                        return redirect(url_for('admin_activities'))
                    else:
                        return redirect(url_for('user_home', user_id=this_user.UserID))
                else:
                    flash("Incorrect password. Please try again.", "danger")
            else:
                flash("User not found. Please register first.", "warning")

        return render_template('login.html')

    # ---------------- LOGOUT ----------------
    @app.route('/logout')
    def logout():
        session.clear()
        flash("You've been logged out.", "success")
        return redirect(url_for('login'))

    # ---------------- REGISTER ----------------
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            email = request.form.get('email')
            password = request.form.get('password')

            this_user = User.query.filter_by(Email=email).first()

            if this_user:
                flash("User already registered. Please login instead.", "warning")
                return redirect(url_for('login'))
            else:
                flash("Registration requires an admin-created vendor account. Please contact your administrator.", "warning")
                return redirect(url_for('login'))

        return render_template('registration.html')

    # ---------------- ADMIN ----------------
    @app.route('/admin', methods=['GET', 'POST'])
    @admin_required
    def admin_activities():
        return render_template('vim_admin_dashboard.html')

    @app.route('/admin/issues', methods=['GET', 'POST'])
    @admin_required
    def admin_vim_issues():
        return render_template('vim_admin_events_dashboard.html')

    @app.route('/admin/users')
    @admin_required
    def admin_user_activities():

        users = User.query.order_by(User.UserID.desc()).all()

        vendors = Vendor.query.order_by(
            Vendor.VendorName
        ).all()

        return render_template(
            'vim_admin_users.html',
            users=users,
            vendors=vendors
        )

    @app.route('/admin/users/add', methods=['POST'])
    @admin_required
    def admin_add_user():

        try:

            user = User(
                Username=request.form['username'],
                Email=request.form['email'],
                PasswordHash=request.form['password'],
                Role=request.form['role'],
                VendorID=int(request.form['vendor_id']),
                IsActive=bool(
                    int(request.form['is_active'])
                )
            )

            db.session.add(user)
            db.session.commit()

            flash(
                "User created successfully.",
                "success"
            )

        except Exception as ex:

            db.session.rollback()

            flash(
                f"Error : {str(ex)}",
                "danger"
            )

        return redirect(
            url_for('admin_user_activities')
        )
        
    @app.route('/admin/users/toggle/<int:user_id>')
    @admin_required
    def admin_toggle_user(user_id):

        user = User.query.get_or_404(user_id)

        user.IsActive = not user.IsActive

        db.session.commit()

        flash(
            "User status updated.",
            "success"
        )

        return redirect(
            url_for('admin_user_activities')
        )
        
    @app.route('/admin/users/delete/<int:user_id>')
    @admin_required
    def admin_delete_user(user_id):

        user = User.query.get_or_404(user_id)

        db.session.delete(user)

        db.session.commit()

        flash(
            "User deleted successfully.",
            "success"
        )

        return redirect(
            url_for('admin_user_activities')
        )
        
    @app.route(
        '/admin/users/edit/<int:user_id>',
        methods=['GET','POST']
    )
    @admin_required
    def admin_edit_user(user_id):

        user = User.query.get_or_404(user_id)

        vendors = Vendor.query.all()

        if request.method == 'POST':

            user.Username = request.form['username']
            user.Email = request.form['email']
            user.Role = request.form['role']
            user.VendorID = request.form['vendor_id']

            db.session.commit()

            flash(
                "User updated successfully.",
                "success"
            )

            return redirect(
                url_for('admin_user_activities')
            )

        return render_template(
            'vim_admin_user_edit.html',
            user=user,
            vendors=vendors
        )
        
    # -----------------VENDOR Management ------------------------
    
    @app.route('/admin/vendors')
    @admin_required
    def admin_vendor_activities():

        vendors = Vendor.query.order_by(
            Vendor.VendorID.desc()
        ).all()

        return render_template(
            'vim_admin_vendors.html',
            vendors=vendors
        )
    
    @app.route(
        '/admin/vendors/add',
        methods=['POST']
    )
    @admin_required
    def admin_add_vendor():

        try:

            vendor = Vendor(
                VendorName=request.form['vendor_name'],
                GSTNumber=request.form['gst_number'],
                Address=request.form['address'],
                Email=request.form['email'],
                PhoneNumber=request.form['phone'],
                Status=int(request.form['status'])
            )

            db.session.add(vendor)

            db.session.commit()

            flash(
                "Vendor added successfully.",
                "success"
            )

        except Exception as ex:

            db.session.rollback()

            flash(
                str(ex),
                "danger"
            )

        return redirect(
            url_for(
                'admin_vendor_activities'
            )
        )
    
    @app.route(
        '/admin/vendors/edit/<int:vendor_id>',
        methods=['GET', 'POST']
    )
    @admin_required
    def admin_edit_vendor(vendor_id):

        vendor = Vendor.query.get_or_404(
            vendor_id
        )

        if request.method == 'POST':

            vendor.VendorName = request.form['vendor_name']
            vendor.GSTNumber = request.form['gst_number']
            vendor.Address = request.form['address']
            vendor.Email = request.form['email']
            vendor.PhoneNumber = request.form['phone']
            vendor.Status = int(
                request.form['status']
            )

            db.session.commit()

            flash(
                "Vendor updated successfully.",
                "success"
            )

            return redirect(
                url_for(
                    'admin_vendor_activities'
                )
            )

        return render_template(
            'vim_admin_vendor_edit.html',
            vendor=vendor
        )
        
    @app.route(
        '/admin/vendors/toggle/<int:vendor_id>'
    )
    @admin_required
    def admin_toggle_vendor(vendor_id):

        vendor = Vendor.query.get_or_404(
            vendor_id
        )

        if vendor.Status == 1:
            vendor.Status = 0
        else:
            vendor.Status = 1

        db.session.commit()

        flash(
            "Vendor status updated.",
            "success"
        )

        return redirect(
            url_for(
                'admin_vendor_activities'
            )
        )
    
    @app.route(
        '/admin/vendors/delete/<int:vendor_id>'
    )
    @admin_required
    def admin_delete_vendor(vendor_id):

        vendor = Vendor.query.get_or_404(
            vendor_id
        )

        try:

            db.session.delete(vendor)

            db.session.commit()

            flash(
                "Vendor deleted successfully.",
                "success"
            )

        except Exception as ex:

            db.session.rollback()

            flash(
                f"Cannot delete vendor. {str(ex)}",
                "danger"
            )

        return redirect(
            url_for(
                'admin_vendor_activities'
            )
        )
    
    # -----------------SYSTEM CONFIGURATION ---------------------
    @app.route(
        '/admin/settings',
        methods=['GET','POST']
    )
    @admin_required
    def admin_settings():

        config = SystemConfiguration.query.first()

        if not config:

            config = SystemConfiguration()

            db.session.add(config)

            db.session.commit()

        if request.method == 'POST':

            config.AppName = request.form[
                'app_name'
            ]

            config.Environment = request.form[
                'environment'
            ]

            config.Currency = request.form[
                'currency'
            ]

            config.LLMProvider = request.form[
                'llm_provider'
            ]

            config.ModelName = request.form[
                'model_name'
            ]

            config.Temperature = float(
                request.form['temperature']
            )

            config.OCRProvider = request.form[
                'ocr_provider'
            ]

            config.ConfidenceThreshold = float(
                request.form[
                    'confidence_threshold'
                ]
            )

            config.ApprovalLevels = int(
                request.form[
                    'approval_levels'
                ]
            )

            config.AutoApproveLimit = float(
                request.form[
                    'auto_approve_limit'
                ]
            )

            config.SMTPServer = request.form[
                'smtp_server'
            ]

            config.SMTPPort = int(
                request.form[
                    'smtp_port'
                ]
            )

            config.OpenAIKey = request.form[
                'openai_key'
            ]

            config.GeminiKey = request.form[
                'gemini_key'
            ]

            db.session.commit()

            flash(
                "Configuration updated successfully.",
                "success"
            )

        return render_template(
            "vim_admin_settings.html",
            config=config
        )
    
    # ---------------- INTELLIGENT INVOICE UPLOAD ----------------
    @app.route('/admin/invoice_upload', methods=['GET', 'POST'])
    @admin_required
    def admin_invoice_upload():
        from flask import current_app
        from vim.extraction import config as extraction_config

        results = []

        # Read directly from ..env file (avoids stale app.config from wrong server instance)
        llama_key, groq_key = extraction_config._read_keys()
        current_app.config["LLAMA_CLOUD_API_KEY"] = llama_key
        current_app.config["GROQ_API_KEY"] = groq_key
        extraction_config.LLAMA_CLOUD_API_KEY = llama_key
        extraction_config.GROQ_API_KEY = groq_key
        keys_ok = bool(llama_key and groq_key)

        if request.method == 'POST' and keys_ok:
            files = request.files.getlist('invoice_files')
            if not files or all(not f.filename for f in files):
                flash("Please select at least one invoice file.", "warning")
                return redirect(url_for('admin_invoice_upload'))

            from vim.extraction.service import process_uploaded_file

            processed_count = 0
            processed_invoice_ids = []

            for f in files:
                if not f.filename:
                    continue

                try:
                    record = process_uploaded_file(f)
                    results.append(record)
                    invoice_id = record.get("invoice_id")
                    if record.get("invoice_id") is not None:
                        processed_count += 1
                        processed_invoice_ids.append(int(invoice_id))

                except ValueError as e:
                    flash(str(e), "danger")

                except OSError as e:
                    flash(str(e).strip(), "danger")
                    break
                except Exception as e:
                    flash(f"Failed to process {f.filename}: {e}","danger")

# --------------------------------------------------
# STORE CURRENT UPLOAD IN SESSION
# --------------------------------------------------
            if processed_invoice_ids:
                session["current_invoice_ids"] = processed_invoice_ids
                session.modified = True
                print("Current uploaded invoice IDs:",processed_invoice_ids)

# --------------------------------------------------
# RUN VALIDATION AFTER ALL UPLOADS ARE PROCESSED
# --------------------------------------------------

            if processed_count:
                try:
                    from vim.validation_setup.validation.run_validation import (
                        run_validation)
                    run_validation()

                    flash(
                        f"Successfully extracted and validated "
                        f"{processed_count} invoice(s).","success")

                except Exception as e:
                    flash(f"Invoices were extracted, but validation failed: {e}","danger")

        elif request.method == 'POST' and not keys_ok:
            flash(
                "API keys not loaded. Save ..env in the project root and restart the server.",
                "danger",
            )

        return render_template('invoice_upload.html', results=results, keys_ok=keys_ok)

    # ---------------- INVOICE DATA EXTRACTION REVIEW ----------------
    @app.route('/admin/invoice_extraction', methods=['GET'])
    @admin_required
    def admin_invoice_extraction():
        from vim.extraction.json_store import load_all, ENRICHED_PATH

        records = load_all()
        rows = []
        for i, rec in enumerate(reversed(records)):
            rows.append({
                "index": len(records) - 1 - i,
                "file_name": rec.get("file_name") or rec.get("stored_file_name") or "—",
                "vendor_name": rec.get("vendor_name") or "—",
                "invoice_number": rec.get("invoice_number") or "—",
                "invoice_date": rec.get("invoice_date") or "—",
                "amount": rec.get("total_due") or "—",
                "currency": rec.get("currency") or "",
                "status": "Failed" if rec.get("_extraction_error") else (
                    "NeedsReview" if rec.get("_validation_issues") else "Success"
                ),
                "line_item_count": len(rec.get("line_items") or []),
            })

        return render_template(
            'invoice_extraction.html',
            extractions=rows,
            json_path=str(ENRICHED_PATH),
        )

    @app.route('/admin/invoice_extraction/<int:record_index>', methods=['GET'])
    @admin_required
    def admin_invoice_extraction_detail(record_index):
        import json
        from vim.extraction.json_store import load_all

        records = load_all()
        if record_index < 0 or record_index >= len(records):
            flash("Extraction record not found.", "warning")
            return redirect(url_for('admin_invoice_extraction'))

        record = records[record_index]
        return render_template(
            'invoice_extraction_detail.html',
            record=record,
            record_index=record_index,
            record_json=json.dumps(record, indent=2, default=str),
        )

    @app.route('/admin/invoice_extraction/download', methods=['GET'])
    @admin_required
    def admin_invoice_extraction_download():
        from flask import send_file
        from vim.extraction.json_store import ENRICHED_PATH, load_all, save_all

        if not ENRICHED_PATH.exists():
            save_all(load_all())
        if not ENRICHED_PATH.exists():
            flash("No extractions yet. Upload an invoice first.", "warning")
            return redirect(url_for('admin_invoice_upload'))

        return send_file(ENRICHED_PATH, as_attachment=True, download_name="enriched.json")

    # ---------------- INVOICE VALIDATION ----------------
    @app.route('/admin/invoice_validation', methods=['GET'])
    @admin_required
    def admin_invoice_validation():
    # --------------------------------------------------
    # GET ONLY THE LATEST UPLOADED INVOICE IDS
    # --------------------------------------------------
        current_invoice_ids = session.get(
            "current_invoice_ids",[])

        print(
            "Invoice Validation - current invoice IDs:",current_invoice_ids)

    # --------------------------------------------------
    # NO CURRENT UPLOAD
    # --------------------------------------------------
        if not current_invoice_ids:
            return render_template("invoice_validation.html",validation_results=[])

    # --------------------------------------------------
    # FETCH ONLY VALIDATION RESULTS FOR CURRENT UPLOAD
    # --------------------------------------------------

        validation_results = (ValidationResult.query.filter(ValidationResult.InvoiceID.in_(current_invoice_ids))
                              .order_by(ValidationResult.ValidationID.desc()).all())

    # --------------------------------------------------
    # CONVERT DB RESULTS TO FRONTEND ROWS
    # --------------------------------------------------

        rows = []
        for result in validation_results:
            rows.append({
                "validation_id": result.ValidationID,
                "invoice_id": result.InvoiceID,
                "invoice_number": result.InvoiceNumber,
                "validation_type": result.ValidationType,
                "status": result.ValidationStatus,
                "message": result.ValidationMessage,
                "validation_date": result.ValidationDate})

        print("Invoice Validation - records displayed:",len(rows))

        return render_template("invoice_validation.html",validation_results=rows)