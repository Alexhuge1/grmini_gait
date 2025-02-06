"""
Copyright (C) [2024] [Fourier Intelligence Ltd.]

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA

--------------------------------------------------

Demo code for Fourier robots

Run this script by:
    python demo_xxx.py --config=config_xxx.yaml
    - config_xxx.yaml is the configuration file for the Fourier robots

"""

import numpy
from ischedule import run_loop, schedule

import fourier_grx.sdk.grmini1.developer as fourier_grx

control_system = fourier_grx.ControlSystem()


def demo_task():
    # 设置机器人算法频率
    control_frequency = 1  # 机器人控制频率, 1Hz
    control_period = 1.0 / control_frequency  # 机器人控制周期

    # 切换为开发者模式，设置机器人数据更新频率
    control_system.developer_mode(servo_on=False, control_frequency=100)

    # 打印版本信息
    print(control_system.get_info())

    # 设置定时任务
    schedule(schedule_task, interval=control_period)

    run_loop()


def schedule_task():
    """
    Update and print state
    """

    """
    Robot States:
    - imu:
      - quat
      - euler angle (rpy) [deg]
      - angular velocity [deg/s]
      - linear acceleration [m/s^2]
    - joint (in urdf):
      - position [deg]
      - velocity [deg/s]
      - torque [Nm]
    - base:
      - position xyz [m]
      - linear velocity xyz [m/s]
    """
    state_dict = control_system.robot_control_loop_get_state()

    # --------------------------------------------------

    robot_num_of_joints = 23

    # parse state
    imu_quat = state_dict.get("imu_quat", [0, 0, 0, 1])
    imu_euler_angle = state_dict.get("imu_euler_angle", [0, 0, 0])
    imu_angular_velocity = state_dict.get("imu_angular_velocity", [0, 0, 0])
    imu_acceleration = state_dict.get("imu_acceleration", [0, 0, 0])
    joint_position = state_dict.get("joint_position", [0] * robot_num_of_joints)
    joint_velocity = state_dict.get("joint_velocity", [0] * robot_num_of_joints)
    joint_kinetic = state_dict.get("joint_kinetic", [0] * robot_num_of_joints)

    # print state
    print("#################################################")
    print("imu_quat = \n", numpy.round(imu_quat, 3))
    print("imu_euler_angle = \n", numpy.round(imu_euler_angle, 3))
    print("imu_angular_velocity = \n", numpy.round(imu_angular_velocity, 3))
    print("imu_acceleration = \n", numpy.round(imu_acceleration, 3))
    print("joint_position = \n", numpy.round(joint_position, 3))
    print("joint_velocity = \n", numpy.round(joint_velocity, 3))
    print("joint_kinetic = \n", numpy.round(joint_kinetic, 3))

    # --------------------------------------------------


if __name__ == "__main__":
    demo_task()
