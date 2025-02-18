import boto3
import json
import argparse
import datetime
import os
import sys

VERSION = "0.1.0"  # 2025-02-18  

class TeeOutput:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, message):
        for stream in self.streams:
            try:
                stream.write(message)
                stream.flush()
            except Exception as e:
                print(f"Error writing to stream: {e}")

    def flush(self):
        for stream in self.streams:
            try:
                stream.flush()
            except Exception as e:
                print(f"Error flushing stream: {e}")

    def close(self):
        for stream in self.streams:
            if hasattr(stream, 'close'):
                try:
                    stream.close()
                except Exception as e:
                    print(f"Error closing stream: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def save_region_resources_to_json(region_data, output_dir="output"):
    """
    Save region-wise AWS resources to a JSON file.

    :param region_data: A dictionary containing resource data for each region.
    :param output_dir: Directory to save the JSON file (default: "output").
    """
    def json_serializer(obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()  # Convert datetime to ISO 8601 string
        raise TypeError(f"Type {type(obj)} not serializable")

    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Generate a timestamped filename
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    filename = f"aws_resources_raw_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    # Save the data to the file
    with open(filepath, "w") as file:
        json.dump(region_data, file, indent=4, default=json_serializer)

    print(f"\nAll Data (JSON formatted) saved to {filepath}")

def list_regions():
    """List all AWS regions with indices."""
    ec2 = boto3.client("ec2")
    regions = ec2.describe_regions()["Regions"]
    region_list = {i + 1: region["RegionName"] for i, region in enumerate(regions)}
    return region_list

def reformat(data, key):
    reformatted_data = []
    
    for item in data:
        if key in item and isinstance(item[key], list):
            list_items = item[key]
            
            # 如果列表只有一个元素，则直接将其转换为字符串
            if len(list_items) == 1:
                new_item = item.copy()  # 拷贝原始字典
                new_item[key] = list_items[0]  # 将 key 的值设置为列表中的唯一元素
                reformatted_data.append(new_item)
            else:
                # 处理第一个元素，保留原来的所有字段
                first_item = item.copy()
                first_item[key] = list_items[0]
                reformatted_data.append(first_item)
                
                # 处理后续元素，只保留 key 字段，其他字段为空

                for value in list_items[1:]:
                    new_item = {k: (value if k == key else item[k] if k == "Name" else "") for k in item}  # 保留 "Name" 和 "key" 字段，其他字段为空
                    reformatted_data.append(new_item)
                
        else:
            # 如果 key 不存在或者不是列表，保留原始项
            reformatted_data.append(item)
    
    return reformatted_data


def print_table(data, sortKey=None):
    """
    Print a table with the given data and headers in a formatted manner.
    The first column values are merged if they are the same as the previous row.

    :param data: List of dictionaries containing the table data.
    :param headers: List of column headers.
    """
    if not data:  # Check if empty
        print("No data available to display.")
        return
    if sortKey:
        data = sorted(data, key=lambda x: x[sortKey])
    headers = list(data[0].keys())
    
    # Compute the maximum width for each column
    col_widths = {header: len(header) for header in headers}  # Initialize with header lengths
    for row in data:
        for header in headers:
            col_widths[header] = max(col_widths[header], len(str(row.get(header, ""))))

    # Create a horizontal separator
    separator = "+".join("-" * (col_widths[header] + 2) for header in headers)
    separator = f"+{separator}+"

    # Print the header row
    print(separator)
    header_row = "| " + " | ".join(f"{header:{col_widths[header]}}" for header in headers) + " |"
    print(header_row)
    #print(separator)

    # Track the previous value of the first column
    prev_vpc = None

    # Print the data rows
    for i, row in enumerate(data):
        # If VPC is the same as the previous row, the first column will be empty
        current_vpc = row.get(headers[0], "")

        if current_vpc == prev_vpc:
            # For rows with the same VPC, only print empty first column
            row_to_print = [""] + [str(row.get(header, "")) for header in headers[1:]]
        else:
            # For new VPC, print full row with VPC value
            row_to_print = [str(row.get(header, "")) for header in headers]
            print(separator)

        # Print the current row
        data_row = "| " + " | ".join(f"{item:{col_widths[header]}}" for item, header in zip(row_to_print, headers)) + " |"
        print(data_row)

        # Update the previous VPC
        prev_vpc = current_vpc

    # Print the closing separator
    print(separator)

def summarize_security_group_rules(security_group):
    # Count Inbound Rules
    inbound_count = len(security_group.get("IpPermissions", []))
    
    # Count Outbound Rules
    outbound_count = len(security_group.get("IpPermissionsEgress", []))
    
    # Format the summary
    summary = f"Inbound Rules: {inbound_count} Outbound Rules: {outbound_count}"
    return summary

def expand_listeners_with_condensed_fields(lbs):
    """
    Expand the 'Listener' field into separate entries for each listener,
    and leave certain fields empty for the second and subsequent rows.
    
    :param lbs: List of Load Balancer dictionaries
    :return: Expanded list of Load Balancer dictionaries with condensed fields
    """
    expanded_lbs = []

    for lb in lbs:
        base_info = {
            "Name": lb["Name"],
            "Type": lb["Type"],
            "Scheme": lb["Scheme"],
            "Vpc" : lb["Vpc"],
            "SecurityGroups": lb["SecurityGroups"],
        }

        # To Multiple lines
        for index, listener in enumerate(lb["Listener"]):
            listener_info = {
                "Listener": f"Port: {listener['Port']}, Protocol: {listener['Protocol']}, Action: {listener['Action']}"
            }

            # 
            if index == 0:
                row_data = {**base_info, **listener_info}
            else:
                row_data = {
                    "Name": lb["Name"],
                    "Type": "",
                    "Scheme": "",
                    "Vpc" : "",
                    "SecurityGroups": "",
                    **listener_info,
                }

            expanded_lbs.append(row_data)

    return expanded_lbs

def collect_ec2_resources(region):
    """Collect EC2 instance information in a region."""
    ec2 = boto3.client("ec2", region_name=region)
    instances = []
    ec2_raw = ec2.describe_instances()["Reservations"]
    for reservation in ec2.describe_instances()["Reservations"]:
        for instance in reservation["Instances"]:
            name = next((tag["Value"] for tag in instance.get("Tags", []) if tag["Key"] == "Name"), "N/A")
            #eni_ids = [eni["NetworkInterfaceId"] for eni in instance.get("NetworkInterfaces", [])]
            ebs_volumes = [volume["Ebs"]["VolumeId"] for volume in instance.get("BlockDeviceMappings", [])]
            subnet = instance.get("SubnetId", "N/A")
            vpc = instance.get("VpcId", "N/A")
            publicIPv4 = instance.get("PublicIpAddress", "N/A")
            ami_id = instance.get("ImageId", "N/A")
            ami_response = ec2.describe_images(ImageIds=[ami_id])
            if ami_response['Images']:
                ami_info = ami_response['Images'][0]  # 取第一个结果
                ami_name = ami_info.get('Name', 'Unknown')  # AMI 名称
                ami_description = ami_info.get('Description', 'No Description')  # AMI 描述
                ami_os = ami_info.get('PlatformDetails', 'Unknown')  # Windows
            instances.append({
                "Name": name,
                "State": instance["State"]["Name"],
                "Type": instance["InstanceType"],
                "OS" : ami_os,
                "InstanceId": instance["InstanceId"],
                "PublicIP": publicIPv4,
                "EBS": ebs_volumes,
                "VPC": vpc,
                "Subnet": subnet,
            })
    return reformat(instances,"EBS"), ec2_raw

def collect_ebs_resources(region):
    """Collect EBS volume information in a region."""
    ec2 = boto3.client("ec2", region_name=region)
    volumes = []
    ebs_raw = ec2.describe_volumes()["Volumes"]

    for volume in ec2.describe_volumes()["Volumes"]:
        #name = next((tag["Value"] for tag in volume.get("Tags", []) if tag["Key"] == "Name"), "N/A")
        volumes.append({
            "VolumeId": volume["VolumeId"],
            #"Name": name,
            "Size(GB)": volume["Size"],
            "IOPS":volume["Iops"],
            "VolumeType":volume["VolumeType"],
            "Attached_Instance":volume["Attachments"][0]["InstanceId"],
        })
    return volumes,ebs_raw

def collect_lb_resources(region):
    """Collect Load Balancer and Target Group information in a region."""
    elbv2 = boto3.client("elbv2", region_name=region)
    ec2 = boto3.client("ec2", region_name=region)
    lb_all = {}

    lbs = []
    lns =[]
    tg_health = []
    target_group_info = []
    lb_all["lb_raw"] = elbv2.describe_load_balancers()["LoadBalancers"]
    lb_all["lb_target_groups"] = elbv2.describe_target_groups()["TargetGroups"]
    

    
    for lb in elbv2.describe_load_balancers()["LoadBalancers"]:
        lsn_info =[]
        lb_all["lb_listener"] = elbv2.describe_listeners(LoadBalancerArn=lb["LoadBalancerArn"])["Listeners"]
        
        for lns in lb_all["lb_listener"]:
            action_type = lns["DefaultActions"][0]["Type"]
            action = action_type

            if action_type == "forward":
                tg_arn = lns["DefaultActions"][0]["TargetGroupArn"]
                tg_name = elbv2.describe_target_groups(TargetGroupArns=[tg_arn])["TargetGroups"][0]['TargetGroupName']
                additional_string=" ("+tg_name+")"
                action = str(action_type) + additional_string
            lsn_info.append({
            #"ListenerArn": lns["ListenerArn"],
            "Port": lns["Port"],
            "Protocol" : lns["Protocol"],
            "Action" : action,
            
            })

        target_groups = elbv2.describe_target_groups(LoadBalancerArn=lb["LoadBalancerArn"])["TargetGroups"]
        
        
        
        for tg in target_groups:
            target_health_descriptions = elbv2.describe_target_health(TargetGroupArn=tg["TargetGroupArn"])["TargetHealthDescriptions"]
            tg_health.append({"TargetGroupName":tg["TargetGroupName"],"Target_health":target_health_descriptions})
            targets = []
            for target in target_health_descriptions:
                instance_id = target.get("Target", {}).get("Id", "N/A")
                if instance_id != "N/A":
                    # Get instance name
                    try:
                        instance_details = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
                        name = next(
                            (tag["Value"] for reservation in instance_details for instance in reservation["Instances"] for tag in instance.get("Tags", []) if tag["Key"] == "Name"),
                            "N/A"
                        )
                    except Exception:
                        name = "N/A"
                else:
                    name = "N/A"

                targets.append(name)

            target_group_info.append({
                "Target Group": tg["TargetGroupName"],
                "Port": tg["Port"],
                "Protocol":tg["Protocol"],
                "Instances": targets,
            })
        
        lbs.append({
            "Name": lb["LoadBalancerName"],
            "Type": lb["Type"],
            "Scheme" : lb["Scheme"],
            "Vpc" : lb["VpcId"],
            "SecurityGroups" :lb["SecurityGroups"],
            "Listener":lsn_info,
            
        })
    lb_all["lb_target_health"]=tg_health
    return lbs,target_group_info, lb_all




def collect_rds_resources(region):
    """Collect RDS instance information in a region."""
    rds = boto3.client("rds", region_name=region)
    ec2 = boto3.client('ec2', region_name=region)
    instances = []
    
    RDS_PORTS = [1521, 3306, 5432, 1433, 6379] 
    rds_raw = rds.describe_db_instances()["DBInstances"]
    for db in rds.describe_db_instances()["DBInstances"]:
        Paired_SG = []
        vpc_security_groups = db.get('VpcSecurityGroups', [])
        for security_group in vpc_security_groups:
            security_group_id = security_group['VpcSecurityGroupId']
            #print(f"Checking Security Group: {security_group_id} for RDS Instance: {db['DBInstanceIdentifier']}")
            
            # 获取 Security Group 的详细信息
            sg_response = ec2.describe_security_groups(GroupIds=[security_group_id])
            
            # 遍历 IpPermissions 并检查 UserIdGroupPairs
            for sg in sg_response['SecurityGroups']:
                for permission in sg.get('IpPermissions', []):
                    from_port = permission.get('FromPort')
                    to_port = permission.get('ToPort')
                    if from_port is not None and to_port is not None:
                        # 如果端口在 RDS 服务端口列表中，则继续检查
                        if from_port == to_port and from_port in RDS_PORTS:
                            for user_group in permission.get('UserIdGroupPairs', []):
                                group_id = user_group.get('GroupId')
                                if group_id:
                                    #print(f"Found GroupId: {group_id} in Security Group: {security_group_id}")
                                    Paired_SG.append(group_id)
        response = ec2.describe_instances(
            Filters=[
                 {
                        "Name": "network-interface.group-id",
                        "Values": Paired_SG
                    }
                ]
        )
        attached_instance_list = []
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                #print(f"Instance ID: {instance['InstanceId']}, State: {instance['State']['Name']}")
                attached_instance_list.append( instance['InstanceId'] )

        instances.append({
            "Name": db["DBInstanceIdentifier"],
            "Engine": db["Engine"],
            "Class": db["DBInstanceClass"],
            "Storage": db["AllocatedStorage"],
            "MultiAZ": db["MultiAZ"],
            "VpcId": db["DBSubnetGroup"]["VpcId"],
            "Connected EC2" : attached_instance_list,
        })
    return reformat(instances,"Connected EC2"),rds_raw

def collect_vpc_resources(region):
    """Collect VPC, Subnet, and SG information in a region."""
    ec2 = boto3.client("ec2", region_name=region)
    vpcs = []
    sgs = []
    Network_resources = {}

    vpc_raw = ec2.describe_vpcs()["Vpcs"]
    subnet_raw = ec2.describe_subnets()["Subnets"]
    IGgateway_raw = ec2.describe_internet_gateways()["InternetGateways"]
    sg_raw = ec2.describe_security_groups()["SecurityGroups"]

    
    Network_resources["vpc_raw"] = vpc_raw
    Network_resources["subnet_raw"] = subnet_raw
    Network_resources["IGgateway_raw"] = IGgateway_raw
    Network_resources["sg_raw"] = sg_raw
    #print(subnet_raw)
    for sb in subnet_raw:
        
        vpc_name = next((tag["Value"] for tag in  ec2.describe_vpcs(VpcIds=[sb["VpcId"]])["Vpcs"][0].get("Tags", []) if tag["Key"] == "Name"), "N/A")
        vpc_combine = vpc_name+"("+sb["VpcId"]+")"
        vpcs.append({
                "vpc":vpc_combine,
                "SubnetName":  next((tag["Value"] for tag in sb.get("Tags", []) if tag["Key"] == "Name"), "N/A"),
                "SubnetId": sb["SubnetId"],
                "CIDR":sb["CidrBlock"],
                "AvailabilityZone" : sb["AvailabilityZone"],
                # "security_group" :security_group_name,
                # "IGW":igw_name,
                # "SecurityGroups": security_groups_info
                # #"SecurityGroups": [{"GroupId": sg[0], "GroupName": sg[1]} for sg in subnet_sgs]
            })
        
    
    for sg in sg_raw:
        vpc_name = next((tag["Value"] for tag in ec2.describe_vpcs(VpcIds=[sg["VpcId"]])["Vpcs"][0].get("Tags", []) if tag["Key"] == "Name"), "N/A")
        vpc_combine = vpc_name+"("+sg["VpcId"]+")"
        sgs.append({
                "AttchedVPC":vpc_combine,
                "Name":  next((tag["Value"] for tag in sg.get("Tags", []) if tag["Key"] == "Name"), "N/A"),
                "Group Name":sg["GroupName"],
                "GroupId": sg["GroupId"],
                "Rules":summarize_security_group_rules(sg),
              })
    return vpcs, sgs, Network_resources

def collect_s3_resources(region):
    s3 = boto3.client('s3', region_name=region)
    all_buckets_info = []
    General_buckets_info = []
    Directory_bucket_info =[]

    # For general bucket
    General_buckets_info = s3.list_buckets()["Buckets"]
    for bucket in General_buckets_info:
        all_buckets_info.append({
            "Name": bucket["Name"],
            "Type": "General Bucket"
        })

#  2025-02-11  Shifeng Hu
# ListDirectoryBucketの機能はReadOnly権限では動作しないため、一時的にコメントアウトしました。
#

#   # # For directory Bucket
    # availableRegion = [ "us-east-1", "us-west-2", "ap-northeast-1", "eu-north-1" ]
    
    # if region in availableRegion:
    #     Directory_bucket_info = s3.list_directory_buckets()["Buckets"]
    #     for bucket in Directory_bucket_info:
    #         all_buckets_info.append({
    #             "Name": bucket["Name"],
    #             "Type": "Directory Bucket"
    #         })
    s3_raw = General_buckets_info + Directory_bucket_info
    return all_buckets_info, s3_raw

def main():
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    logfilename = f"aws_resources_{timestamp}.log"
    all_region_rawdata= []
    parser = argparse.ArgumentParser(description="AWS Resource Collector")
    parser.add_argument("-l", action="store_true", help="List all AWS regions")
    parser.add_argument("-r", nargs="+", help="Specify region indices or names to list resources")
    parser.add_argument("-v", "--version", action="store_true", help="Show version information") 
    args = parser.parse_args()

    if args.version:
        print(f"AWS Resource Collector Version: {VERSION}")
        sys.exit(0)

    if len(sys.argv) == 1:   # Check if specify some parameters
        parser.print_help()  # No Parameters
        sys.exit(1)          

    regions = list_regions()

    if args.l:
        for idx, region in regions.items():
            print(f"{idx}: {region}")
        return

    if args.r:
        # Convert region indices to region names
        selected_regions = []
        if "all" in args.r:
            print("This will collect all regions information, it will take longer times.\n")
            selected_regions = list(regions.values())
        else:    
            for r in args.r:
                if r.isdigit():
                    selected_regions.append(regions.get(int(r), "Unknown"))
                else:
                    selected_regions.append(r)
        log_path = os.path.join("./output", logfilename)
        os.makedirs("./output", exist_ok=True)
        log_file = open(log_path, "a")
        sys.stdout = TeeOutput(sys.stdout, log_file)
        sys.stderr = TeeOutput(sys.stderr, log_file)

        for region in selected_regions:
            print(f"\n{'-'*30} {region} {'-'*30}")
            region_resources = {"region": region, "collected_resources": {}}

            ec2_data, region_resources["collected_resources"]["ec2"] = collect_ec2_resources(region)
            print("\nEC2 Instances:")
            print_table(ec2_data)

            ebs_data, region_resources["collected_resources"]["ebs"] = collect_ebs_resources(region)            
            print("\nEBS Volumes:")
            print_table(ebs_data)

            rds_data, region_resources["collected_resources"]["rds"] = collect_rds_resources(region)
            print("\nRDS Instances:")
            print_table(rds_data)

            vpc_data, sgs_data, region_resources["collected_resources"]["network"] = collect_vpc_resources(region)
            print("\nVPCs:")
            print_table(vpc_data, sortKey="vpc")

            print("\nSecurity Groups:")
            print_table(sgs_data,sortKey="AttchedVPC")
            
            lb_data, tg_info, region_resources["collected_resources"]["loadbalancer"] = collect_lb_resources(region)     
            print("\nLoad Balancers:")
            print_table(expand_listeners_with_condensed_fields(lb_data))
            print_table(tg_info)

            s3_data , region_resources["collected_resources"]["s3"] = collect_s3_resources(region)
            print("\nS3 Information:")
            print_table(s3_data)

            all_region_rawdata.append(region_resources)

        save_region_resources_to_json(all_region_rawdata)
        #log_file.close()
if __name__ == "__main__":
    main()
