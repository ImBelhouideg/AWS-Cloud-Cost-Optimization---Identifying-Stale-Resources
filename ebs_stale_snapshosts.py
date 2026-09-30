# Triggered by: Amazon EventBridge scheduled rule (cron)
# Purpose: Automated cost optimization — removes stale EBS snapshots
# Author: Imad Eddine Belhouideg
#
# Required IAM permissions (least-privilege):
# - ec2:DescribeSnapshots
# - ec2:DescribeInstances  
# - ec2:DescribeVolumes
# - ec2:DeleteSnapshot

import boto3

def lambda_handler(event, context):
    ec2 = boto3.client('ec2')

    # Get all EBS snapshots owned by this account
    response = ec2.describe_snapshots(OwnerIds=['self'])

    # Get all active EC2 instance IDs (running AND stopped)
    instances_response = ec2.describe_instances(
        Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped']}]
    )
    active_instance_ids = set()

    for reservation in instances_response['Reservations']:
        for instance in reservation['Instances']:
            active_instance_ids.add(instance['InstanceId'])

    # Iterate through each snapshot and delete if stale
    for snapshot in response['Snapshots']:
        snapshot_id = snapshot['SnapshotId']
        volume_id = snapshot.get('VolumeId')

        if not volume_id:
            # Snapshot not attached to any volume → delete
            ec2.delete_snapshot(SnapshotId=snapshot_id)
            print(f"Deleted EBS snapshot {snapshot_id} as it was not attached to any volume.")
        else:
            try:
                volume_response = ec2.describe_volumes(VolumeIds=[volume_id])
                attachments = volume_response['Volumes'][0]['Attachments']

                if not attachments:
                    # Volume exists but not attached to any instance → delete
                    ec2.delete_snapshot(SnapshotId=snapshot_id)
                    print(f"Deleted EBS snapshot {snapshot_id} as its volume is not attached to any instance.")
                else:
                    # Check if the attached instance is still active
                    attached_instance_id = attachments[0]['InstanceId']
                    if attached_instance_id not in active_instance_ids:
                        ec2.delete_snapshot(SnapshotId=snapshot_id)
                        print(f"Deleted EBS snapshot {snapshot_id} as its instance {attached_instance_id} is not active.")

            except ec2.exceptions.ClientError as e:
                if e.response['Error']['Code'] == 'InvalidVolume.NotFound':
                    # Volume was deleted → snapshot is orphaned → delete
                    ec2.delete_snapshot(SnapshotId=snapshot_id)
                    print(f"Deleted EBS snapshot {snapshot_id} as its associated volume was not found.")
