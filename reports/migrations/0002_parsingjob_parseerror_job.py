# Generated manually for ParsingJob model

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ParsingJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('task_id', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('PROCESSING', 'Processing'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed')], default='PENDING', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('uploaded_files', models.JSONField(default=list)),
                ('result_excel', models.FileField(blank=True, null=True, upload_to='results/')),
                ('result_csv', models.FileField(blank=True, null=True, upload_to='results/')),
                ('total_files', models.IntegerField(default=0)),
                ('total_drives', models.IntegerField(default=0)),
                ('duplicates_removed', models.IntegerField(default=0)),
                ('error_message', models.TextField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='parsingjob',
            index=models.Index(fields=['-created_at'], name='reports_par_created_d3a46f_idx'),
        ),
        migrations.AddIndex(
            model_name='parsingjob',
            index=models.Index(fields=['status'], name='reports_par_status_856aa9_idx'),
        ),
        migrations.AddField(
            model_name='parseerror',
            name='job',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='errors', to='reports.parsingjob'),
        ),
        migrations.AlterField(
            model_name='parseerror',
            name='batch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='errors', to='reports.uploadbatch'),
        ),
    ]

