import argparse
import boto3
from tabulate import tabulate
import graphviz

# Function to list AWS regions
def list_regions():
    ec2 = boto3.client('ec2')
    response = ec2.describe_regions()
    regions = [region['RegionName'] for region in response['Regions']]
    return regions

# Function to collect resources from a specific region
def collect_resources(region):
    ec2 = boto3.client('ec2', region_name=region)
    rds = boto3.client('rds', region_name=region)
    elb = boto3.client('elbv2', region_name=region)

    # Collect EC2 instances
    ec2_instances = ec2.describe_instances()
    ec2_data = []
    for reservation in ec2_instances['Reservations']:
        for instance in reservation['Instances']:
            instance_name = next((tag['Value'] for tag in instance.get('Tags', []) if tag['Key'] == 'Name'), 'N/A')
            instance_id = instance['InstanceId']
            instance_type = instance['InstanceType']
            public_ip = instance.get('PublicIpAddress', 'N/A')
            vpc_id = instance['VpcId']
            subnet_id = instance['SubnetId']
            
            # Ensure 'VolumeId' exists before adding to list
            ebs_volumes = []
            for volume in instance.get('BlockDeviceMappings', []):
                if 'Ebs' in volume and 'VolumeId' in volume['Ebs']:
                    ebs_volumes.append(volume['Ebs']['VolumeId'])

            ec2_data.append({
                'Name': instance_name,
                'InstanceId': instance_id,
                'InstanceType': instance_type,
                'PublicIP': public_ip,
                'VPC': vpc_id,
                'Subnet': subnet_id,
                'EBS Volumes': ', '.join(ebs_volumes)
            })

    # Collect RDS instances
    rds_instances = rds.describe_db_instances()
    rds_data = []
    for db_instance in rds_instances['DBInstances']:
        rds_data.append({
            'DBInstanceIdentifier': db_instance['DBInstanceIdentifier'],
            'Engine': db_instance['Engine'],
            'Status': db_instance['DBInstanceStatus'],
        })

    # Collect Load Balancers
    lb_data = []
    load_balancers = elb.describe_load_balancers()
    for lb in load_balancers['LoadBalancers']:
        lb_name = lb['LoadBalancerName']
        lb_arn = lb['LoadBalancerArn']
        target_groups = elb.describe_target_groups(LoadBalancerArn=lb_arn)['TargetGroups']
        target_group_names = [tg['TargetGroupName'] for tg in target_groups]

        lb_data.append({
            'LoadBalancer': lb_name,
            'ARN': lb_arn,
            'TargetGroups': ', '.join(target_group_names)
        })

    return ec2_data, rds_data, lb_data

# Function to draw graph using Graphviz
def draw_graph(ec2_data, rds_data, lb_data):
    dot = graphviz.Digraph(comment='AWS Topology')

    # Add EC2 instances and relationships
    with dot.subgraph() as s:
        s.attr(rankdir='LR')
        for instance in ec2_data:
            # Create EC2 instance node
            instance_node = f"{instance['InstanceId']} ({instance['Name']})"
            dot.node(instance_node, f"EC2: {instance['Name']} ({instance['InstanceId']})")

            # Add EBS volumes as nodes
            for volume in instance['EBS Volumes'].split(', '):
                ebs_node = f"Volume: {volume}"
                dot.node(ebs_node, f"EBS: {volume}")
                dot.edge(instance_node, ebs_node)  # Connect EC2 to EBS

            # Connect EC2 to Subnet (displayed as a box)
            subnet_node = f"Subnet: {instance['Subnet']}"
            dot.node(subnet_node, f"Subnet: {instance['Subnet']}")
            dot.edge(instance_node, subnet_node)

    # Add Load Balancers and target groups
    with dot.subgraph() as s:
        s.attr(rankdir='LR')
        for lb in lb_data:
            lb_node = lb['LoadBalancer']
            dot.node(lb_node, f"LB: {lb_node}")
            for target_group in lb['TargetGroups'].split(', '):
                tg_node = f"TG: {target_group}"
                dot.node(tg_node, f"Target Group: {target_group}")
                dot.edge(lb_node, tg_node)  # Connect LB to Target Group
                
                # Assuming EC2s in the Target Group
                for instance in ec2_data:
                    if lb_node in instance['EBS Volumes']:  # Example of EC2 in Target Group
                        dot.edge(tg_node, instance['InstanceId'])  # Connect TG to EC2

    # Render the graph to a file and display it
    dot.render('/tmp/aws_topology', view=True)

# Main function to handle argument parsing and execution
def main():
    parser = argparse.ArgumentParser(description="AWS Resource Collector and Visualizer")
    parser.add_argument('-r', '--region', type=int, nargs='+', help="Specify region(s) by number", required=False)
    parser.add_argument('-d', '--draw', action='store_true', help="Draw the topology graph")
    parser.add_argument('-l', '--list', action='store_true', help="List all available AWS regions")
    args = parser.parse_args()

    # List all available AWS regions
    if args.list:
        regions = list_regions()
        print("Available regions:")
        for i, region in enumerate(regions, start=1):
            print(f"{i}: {region}")
        return

    # List all available regions and collect resources if -r is provided
    if args.region:
        regions = list_regions()
        for region_index in args.region:
            region = regions[region_index - 1]
            print(f"Collecting resources for region: {region}")

            # Collect the resources in the selected region
            ec2_data, rds_data, lb_data = collect_resources(region)

            # Display the resource tables
            print("\nEC2 Instances:")
            print(tabulate(ec2_data, headers="keys", tablefmt="pretty"))
            print("\nRDS Instances:")
            print(tabulate(rds_data, headers="keys", tablefmt="pretty"))
            print("\nLoad Balancers:")
            print(tabulate(lb_data, headers="keys", tablefmt="pretty"))

            # If -d is provided, draw the graph
            if args.draw:
                draw_graph(ec2_data, rds_data, lb_data)

if __name__ == "__main__":
    main()