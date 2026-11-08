# Deploying to AWS EC2

Matches the plan in [`docs/spec.md`](../docs/spec.md) §6-7: one EC2 instance running Postgres, Nginx, and Gunicorn — no RDS, no other AWS services. Free for the first 12 months under the AWS Free Tier; ~$6-9/month after that.

## 1. Launch the instance

Two ways to do this — pick one. Both produce the same thing: one Ubuntu EC2 instance, a security group (SSH from your IP only, HTTP/HTTPS from anywhere), and an Elastic IP.

### Option A — Terraform (recommended)

Infrastructure as code: the instance, security group, and Elastic IP are all defined in [`terraform/`](../terraform/) and reproducible from a single `terraform apply`. Requires [Terraform](https://developer.hashicorp.com/terraform/install) installed locally and AWS credentials configured (`aws configure`, or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` env vars) for an IAM user with EC2 permissions.

1. In the EC2 console, create a key pair first if you don't have one (**Key Pairs → Create key pair**) — Terraform references an existing key pair by name rather than creating one, since the private key must be downloaded once and kept safe.
2. Find your own public IP (for the SSH security group rule): `curl https://checkip.amazonaws.com`
3. ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # edit terraform.tfvars: key_name and ssh_allowed_cidr at minimum
   terraform init
   terraform plan    # review what it will create
   terraform apply   # type yes to confirm
   ```
4. Note the `public_ip` output — that's your Elastic IP. (Optional but recommended) Point a domain's **A record** at it now, so it has time to propagate before Certbot in step 4 below.
5. Skip to **step 2** below using the IP/key from this output.

To tear the instance down later (e.g. to stop paying before the free tier ends, or to rebuild from scratch): `terraform destroy` — this deletes the instance, security group, and releases the Elastic IP. Your database lives only on that instance's disk, so take a backup first (see §7) if you don't want to lose it.

### Option B — AWS Console (manual, no Terraform)

1. **EC2 → Launch instance**
   - AMI: **Ubuntu Server 22.04 or 24.04 LTS**
   - Instance type: **t3.micro** (x86) or **t4g.micro** (ARM, slightly cheaper, still free-tier eligible) — either works, the app has no architecture-specific dependencies
   - Key pair: create or reuse one (needed for SSH)
   - Storage: default 8-30GB gp3 is plenty
   - **Security group**: allow inbound
     - SSH (22) — from your IP only, not `0.0.0.0/0`
     - HTTP (80) — from anywhere
     - HTTPS (443) — from anywhere
2. **Allocate an Elastic IP** and associate it with the instance, so the IP survives reboots/stop-start and your domain's DNS stays valid.
3. (Optional but recommended) Point a domain's **A record** at the Elastic IP now, so it has time to propagate before you run Certbot in step 4.

## 2. First login and clone the repo

```bash
ssh -i your-key.pem ubuntu@<elastic-ip>
sudo mkdir -p /opt/ssm-crm
sudo chown ubuntu:ubuntu /opt/ssm-crm
git clone https://github.com/aravindarcbe/dummy-crm /opt/ssm-crm
cd /opt/ssm-crm
```

## 3. Set required environment variables and provision

```bash
export DB_PASSWORD='choose-a-strong-password'
sudo -E ./deploy/provision.sh
```

This installs Postgres/Nginx/Certbot, creates the `ssm_crm` database, sets up the Python virtualenv, runs migrations, installs the `ssm-crm` systemd service and Nginx site, and sets up the nightly backup cron job. It prints the remaining manual steps at the end — repeated here:

## 4. Finish the manual steps provision.sh can't do for you

1. **Edit `/opt/ssm-crm/webapp/.env`** with real values (it was seeded from `.env.example`):
   ```
   DJANGO_SECRET_KEY=<generate one — e.g. `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`>
   DJANGO_DEBUG=False
   DJANGO_ALLOWED_HOSTS=your-domain.com
   DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com
   COMPANY_NAME=SSM Centring Rentals
   DB_ENGINE=postgres
   DB_NAME=ssm_crm
   DB_USER=ssm_crm
   DB_PASSWORD=<same password you exported above>
   DB_HOST=localhost
   DB_PORT=5432
   ```
   Then: `sudo systemctl restart ssm-crm`

2. **Edit `/etc/nginx/sites-available/ssm-crm`**, replace `YOUR_DOMAIN` with your real domain, then:
   ```bash
   sudo nginx -t && sudo systemctl reload nginx
   ```

3. **Add HTTPS** once DNS is pointed at the instance:
   ```bash
   sudo certbot --nginx -d your-domain.com
   ```
   Certbot edits the Nginx config in place to add the TLS server block and sets up auto-renewal via a systemd timer — no cron needed for renewal.

4. **Create the first admin login:**
   ```bash
   cd /opt/ssm-crm/webapp
   sudo -u ssmcrm .venv/bin/python manage.py createsuperuser
   ```

5. **Load data** — either the owner's real Excel tracker or made-up demo data (pick one, not both, against a fresh database):
   ```bash
   sudo -u ssmcrm .venv/bin/python manage.py import_excel_data   # real data
   # or
   sudo -u ssmcrm .venv/bin/python manage.py seed_demo_data      # demo data
   ```

## 5. Verify

- `sudo systemctl status ssm-crm` — should be `active (running)`
- `curl -I http://localhost` on the instance — should get a response from Gunicorn via the Nginx proxy
- Visit `https://your-domain.com/` and `https://your-domain.com/admin/` from a browser

## 6. Deploying future changes

No CI/CD pipeline yet (per spec.md §6, manual deploy to start). To ship a change:

```bash
ssh ubuntu@<elastic-ip>
cd /opt/ssm-crm
sudo -u ssmcrm git pull origin main
sudo -u ssmcrm /opt/ssm-crm/webapp/.venv/bin/pip install -r webapp/requirements.txt
sudo -u ssmcrm /opt/ssm-crm/webapp/.venv/bin/python webapp/manage.py migrate
sudo -u ssmcrm /opt/ssm-crm/webapp/.venv/bin/python webapp/manage.py collectstatic --noinput
sudo systemctl restart ssm-crm
```

## 7. Backups

`deploy/backup/pg_backup.sh` runs nightly via cron (installed by `provision.sh`), dumping to `/opt/ssm-crm/backups/` and keeping 14 days locally. To also push dumps to S3, set `AWS_S3_BACKUP_BUCKET=your-bucket-name` in the crontab's environment and ensure the instance's IAM role (or the `aws` CLI's configured credentials) has write access to that bucket.

## Troubleshooting

- **502 Bad Gateway**: Gunicorn isn't running or the socket path is wrong — check `sudo systemctl status ssm-crm` and `sudo journalctl -u ssm-crm -n 50`.
- **Static files 404**: did `collectstatic` run? Check `/opt/ssm-crm/webapp/staticfiles/` has content and matches the `alias` path in the Nginx config.
- **"CSRF verification failed"**: `DJANGO_CSRF_TRUSTED_ORIGINS` in `.env` must include your `https://` domain.
