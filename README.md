# Wormhole Queue System

**A real-time help queue for Oregon State University's Physics Wormhole that helps students request tutoring support and helps Wormhole Assistants respond in a clear, fair order.**

Wormhole Queue System replaces an outdated tutoring queue workflow with a web-based system for student help requests, live queue visibility, assistant ticket handling, and administrative record keeping. It is designed for the OSU Physics Wormhole, where students need a simple way to ask for help and staff need a reliable way to manage requests during busy tutoring hours.

## Use Wormhole

- [Submit a help request](https://wormhole.physics.oregonstate.edu/createticket)
- [View the live queue](https://wormhole.physics.oregonstate.edu/livequeue)
- [Visit the live site](https://wormhole.physics.oregonstate.edu/)
- [View the source code](https://github.com/FarisNasse/CS461-wormhole-queue-system)

![Blue digital wormhole graphic used as the project header image.](app/static/Updated-Wormhole-Image.png)

## At a Glance

| Audience | What Wormhole Queue System helps them do |
|---|---|
| Students | Request tutoring help and see queue activity without needing to guess whether their request was received. |
| Wormhole Assistants | Claim, manage, and resolve help requests through a shared ticket workflow. |
| Administrators | Manage assistant accounts, review queue activity, export records, and keep the system maintainable for future terms. |

## Why This Project Matters

The Physics Wormhole is a tutoring and collaboration space where students can get support with physics coursework. During busy periods, a help center needs more than an informal line or a hand-raised system. Students need to know that their request was received, Wormhole Assistants need to know who should be helped next, and administrators need records that make the system easier to review and maintain.

Wormhole Queue System solves that problem by giving the help center a single public-facing queue workflow. Students can submit a request, assistants can manage the queue in order, and administrators can keep the system organized without relying on scattered manual processes.

The result is a help queue that is easier for students to trust, easier for assistants to operate, and easier for future maintainers to improve.

## Key Features

- **Request help without confusion:** Students can submit a help request with their name, physics course, and location through the web form or supported Wormhole button boxes.
- **View queue activity in real time:** Students can open the live queue to see current help requests and better understand what is happening during busy tutoring hours.
- **Give assistants a shared workflow:** Wormhole Assistants can claim tickets, return tickets to the queue, and resolve tickets as helped, duplicate, or no-show.
- **Support administrative oversight:** Admin users can manage assistant accounts, review active users, monitor hardware status, clear queue data, and export archived ticket records.
- **Make future maintenance easier:** The project is built as a documented Flask application with database migrations, automated tests, linting tools, and deployment documentation so future Wormhole teams can continue improving it.

## Project Demo

The demo below shows one way a student help request can enter the queue: a physical Wormhole button box submits a request that becomes visible to the system.

![Demo of a Wormhole table button box submitting a student help request.](assets/button_box.gif)

**Demo description:** A Wormhole button box is used to submit a student help request. The request is sent into the queue so Wormhole Assistants can see it, claim it, and resolve it.

A typical request moves through the system like this:

1. A student submits a help request from the website or a Wormhole button box.
2. The request appears in the queue.
3. A Wormhole Assistant claims the ticket.
4. The assistant helps the student.
5. The assistant resolves the ticket, and the system keeps the record for review or export.

## How to Access or Try It

### Live Site

The public site is available at: <https://wormhole.physics.oregonstate.edu/>

Students can use the live site to submit a help request or view queue activity. Wormhole Assistants and administrators need approved accounts to access staff-only tools.

### Main Entry Points

| Page | Purpose |
|---|---|
| [Submit a help request](https://wormhole.physics.oregonstate.edu/createticket) | Students can enter the queue by submitting their name, course, and location. |
| [Live queue](https://wormhole.physics.oregonstate.edu/livequeue) | Students and staff can view current queue activity. |
| [Project repository](https://github.com/FarisNasse/CS461-wormhole-queue-system) | Developers and reviewers can inspect the source code. |

### Local Development

To run the project locally on macOS/Linux:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
flask db upgrade
flask run
```

On Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask db upgrade
flask run
```

The local development server uses plain HTTP by default:

```text
http://127.0.0.1:5000
```

If a browser keeps trying HTTPS after a previous redirect, clear the browser's cached site data for `127.0.0.1` / `localhost`, open an incognito window, or run Flask on a different port, such as `flask run --port 5001`.

For production deployment, configure environment variables such as `APP_ENV=production`, `SECRET_KEY`, `DATABASE_URL`, `FORCE_HTTPS=1`, `ENABLE_HSTS=1`, `SESSION_COOKIE_SECURE=1`, and `PREFERRED_URL_SCHEME=https`. See the deployment documentation in `deploy/` for more details.

### Forgot-Password Email Configuration

Password reset emails are sent through Amazon SES. The production sender should use the verified `physics.oregonstate.edu` SES domain identity:

```env
SES_REGION=us-west-2
MAIL_DEFAULT_SENDER="Wormhole Physics <no-reply@physics.oregonstate.edu>"
MAIL_REPLY_TO="Wormhole Physics <Wormhole.Physics@oregonstate.edu>"
EMAIL_ENABLED=1
RESET_PASSWORD_TOKEN_MAX_AGE=3600
```

`MAIL_DEFAULT_SENDER` is the automated transactional sender. `MAIL_REPLY_TO` routes human replies to the monitored Wormhole inbox. Do not commit AWS access keys or any real secret values. On AWS, credentials should come from the instance role, Elastic Beanstalk environment, Parameter Store, Secrets Manager, or another approved deployment mechanism.

## System Requirements

- Python 3.12 or newer
- Flask and project dependencies from `requirements.txt`
- A configured database for non-testing deployment
- A modern web browser for student, assistant, and admin users
- Approved Wormhole Assistant or administrator credentials for staff-only tools

## Built With

| Area | Tools |
|---|---|
| Backend | Python, Flask, SQLAlchemy, Flask-Migrate |
| Real-time queue behavior | Flask-SocketIO |
| Frontend | Jinja2 templates, HTML, CSS, JavaScript |
| Testing and quality checks | Pytest, Ruff, MyPy, djLint, Stylelint, Playwright, Locust |
| Deployment support | Gunicorn, Nginx/systemd documentation, environment-based configuration |

## Project Impact

Wormhole Queue System is valuable because it focuses on the actual experience of a tutoring center:

- Students get a clearer path to asking for help.
- Assistants get a shared queue instead of relying on memory or informal ordering.
- Administrators get better visibility into queue activity and user management.
- Future maintainers get a Python-based codebase with documentation and automated quality checks.

This makes the project more than a class assignment. It is a practical tool for keeping an academic help center organized, transparent, and easier to maintain.

## Team Credits

| Team Member | Role |
|---|---|
| [Faris Nasse](https://github.com/FarisNasse) | Hardware coordination; software development and code review |
| [Graham Glazner](https://github.com/GrahamAtOSU) | Documentation coordination; software development and code review |
| [Jonathan Hotchkiss](https://github.com/hotchkjo) | Team lead and communication; software development and code review |
| [Alexey Leeper](https://github.com/alexeyjleeper) | Testing coordination; software development and code review |

This project was developed for Oregon State University's Physics Wormhole, a physics collaboration and help center that supports students during tutoring hours.

## Feedback and Contact

For bugs, feature ideas, or maintenance notes, open an issue in the project repository:

[Open a GitHub issue](https://github.com/FarisNasse/CS461-wormhole-queue-system/issues)

For project-specific questions, contact the current Wormhole project team through the OSU Physics Help Center.

## Accessibility Notes

This README uses descriptive links, alt text for images, and a written description of the animated demo. The live site is designed to be usable from a modern web browser on desktop or mobile devices.
