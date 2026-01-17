"""
Admin API - Scheduler kontrola.

Endpointi za monitoring i manuelno pokretanje scheduler jobova.
"""

from flask import jsonify, request
from . import bp
from ..middleware.admin_auth import admin_required


@bp.route('/scheduler/status', methods=['GET'])
@admin_required()
def get_scheduler_status(admin):
    """
    Vraca status schedulera i svih jobova.

    Response:
        {
            "running": true,
            "jobs": [
                {
                    "id": "billing_daily",
                    "name": "Dnevne billing provere",
                    "next_run": "2026-01-18T06:00:00",
                    "trigger": "cron[hour='6', minute='0']"
                },
                ...
            ]
        }
    """
    from ...services.scheduler_service import get_scheduler_status
    return jsonify(get_scheduler_status())


@bp.route('/scheduler/run/<job_id>', methods=['POST'])
@admin_required(roles=['SUPER_ADMIN'])
def run_job_manually(admin, job_id):
    """
    Pokrece job manuelno (van rasporeda).

    Samo SUPER_ADMIN moze pokretati jobove manuelno.

    Args:
        job_id: ID joba (billing_daily, generate_invoices, send_reminders)

    Response:
        {"success": true, "message": "Job billing_daily pokrenut"}
    """
    from ...services.scheduler_service import run_job_now

    valid_jobs = ['billing_daily', 'generate_invoices', 'send_reminders']
    if job_id not in valid_jobs:
        return jsonify({
            'error': f'Nepoznat job: {job_id}',
            'valid_jobs': valid_jobs
        }), 400

    success = run_job_now(job_id)
    if success:
        return jsonify({
            'success': True,
            'message': f'Job {job_id} pokrenut'
        })
    else:
        return jsonify({
            'error': f'Job {job_id} nije pronadjen ili scheduler nije pokrenut'
        }), 404
