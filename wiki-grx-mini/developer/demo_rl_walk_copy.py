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

这个 demo 要求连接摇杆, 用摇杆控制机器人走路速度

"""

import os
import numpy
import torch
from ischedule import run_loop, schedule
import fourier_grx.sdk.grmini1.developer as fourier_grx
from collections import deque
from scipy.spatial.transform import Rotation as R

# 假设这里有 XBotLCfg 类的定义，根据实际情况调整
class XBotLCfg:
    class env:
        num_actions = 12
        num_single_obs = 47
        num_observations = num_single_obs * 5
        frame_stack = 5
    class normalization:
        class obs_scales:
            lin_vel = 1.0
            ang_vel = 1.0
            dof_pos = 1.0
            dof_vel = 1.0
        clip_observations = 1000.0
        clip_actions = 1.0
    class control:
        action_scale = 1.0
    class robot_config:
        kps = numpy.array([200, 200, 350, 350, 15, 15, 200, 200, 350, 350, 15, 15], dtype=numpy.double)
        kds = numpy.array([10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10], dtype=numpy.double)
        tau_limit = 200. * numpy.ones(12, dtype=numpy.double)


class cmd:
    vx = 0.4
    vy = 0.0
    dyaw = 0.0


def quaternion_to_euler_array(quat):
    # Ensure quaternion is in the correct format [x, y, z, w]
    x, y, z, w = quat

    # Roll (x-axis rotation)
    t0 = +2.0 * (w * x + y * z)
    t1 = +1.0 - 2.0 * (x * x + y * y)
    roll_x = numpy.arctan2(t0, t1)

    # Pitch (y-axis rotation)
    t2 = +2.0 * (w * y - z * x)
    t2 = numpy.clip(t2, -1.0, 1.0)
    pitch_y = numpy.arcsin(t2)

    # Yaw (z-axis rotation)
    t3 = +2.0 * (w * z + x * y)
    t4 = +1.0 - 2.0 * (y * y + z * z)
    yaw_z = numpy.arctan2(t3, t4)

    # Returns roll, pitch, yaw in a NumPy array in radians
    return numpy.array([roll_x, pitch_y, yaw_z])


control_system = fourier_grx.ControlSystem()

policy_file_path = None
policy_model = None
policy_action = None
obs_buf_stack = None


def main():
    global policy_file_path, policy_model

    # 设置机器人算法频率
    target_control_frequency = 50  # 机器人控制频率, 50Hz
    target_control_period_in_s = 1.0 / target_control_frequency  # 机器人控制周期

    # 切换为开发者模式，设置机器人数据更新频率
    control_system.developer_mode(servo_on=True, control_frequency=100)

    # 打印版本信息
    print(control_system.get_info())

    # Load Model
    policy_file_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "policy_jit_rl_walk.pt",
    )

    policy_model = torch.jit.load(policy_file_path, map_location=torch.device('cpu'))

    # 设置定时任务
    schedule(algorithm, interval=target_control_period_in_s)

    run_loop()


def algorithm():
    global policy_model, policy_action, obs_buf_stack

    # update state
    """
    state:
    - imu:
      - quat (x, y, z, w)
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
    policy_control_num_of_joints = 12  # 调整为 12 以匹配新模型

    # get states
    imu_measured_quat = state_dict.get("imu_quat", [0, 0, 0, 1])
    imu_measured_angular_velocity = state_dict.get("imu_angular_velocity", [0, 0, 0])
    joint_measured_position = state_dict.get("joint_position", [0] * robot_num_of_joints)
    joint_measured_velocity = state_dict.get("joint_velocity", [0] * robot_num_of_joints)

    # 只取需要的关节数据
    joint_measured_position = joint_measured_position[-policy_control_num_of_joints:]
    joint_measured_velocity = joint_measured_velocity[-policy_control_num_of_joints:]

    # --------------------------------------------------

    hist_obs = deque()
    for _ in range(XBotLCfg.env.frame_stack):
        hist_obs.append(numpy.zeros([1, XBotLCfg.env.num_single_obs], dtype=numpy.double))

    count_lowlevel = 0

    # 1000hz -> 100hz
    if count_lowlevel % 20 == 0:  # 假设这里的 decimation 为 20，根据实际情况调整
        obs = numpy.zeros([1, XBotLCfg.env.num_single_obs], dtype=numpy.float32)
        eu_ang = quaternion_to_euler_array(imu_measured_quat)
        eu_ang[eu_ang > numpy.pi] -= 2 * numpy.pi

        obs[0, 0] = numpy.sin(2 * numpy.pi * count_lowlevel * 0.001 / 0.64)
        obs[0, 1] = numpy.cos(2 * numpy.pi * count_lowlevel * 0.001 / 0.64)
        obs[0, 2] = cmd.vx * XBotLCfg.normalization.obs_scales.lin_vel
        obs[0, 3] = cmd.vy * XBotLCfg.normalization.obs_scales.lin_vel
        obs[0, 4] = cmd.dyaw * XBotLCfg.normalization.obs_scales.ang_vel
        obs[0, 5:17] = numpy.radians(joint_measured_position) * XBotLCfg.normalization.obs_scales.dof_pos
        obs[0, 17:29] = numpy.radians(joint_measured_velocity) * XBotLCfg.normalization.obs_scales.dof_vel
        obs[0, 29:41] = policy_action if policy_action is not None else numpy.zeros(policy_control_num_of_joints)
        obs[0, 41:44] = numpy.radians(imu_measured_angular_velocity)
        obs[0, 44:47] = eu_ang

        obs = numpy.clip(obs, -XBotLCfg.normalization.clip_observations, XBotLCfg.normalization.clip_observations)

        hist_obs.append(obs)
        hist_obs.popleft()

        policy_input = numpy.zeros([1, XBotLCfg.env.num_observations], dtype=numpy.float32)
        for i in range(XBotLCfg.env.frame_stack):
            policy_input[0, i * XBotLCfg.env.num_single_obs: (i + 1) * XBotLCfg.env.num_single_obs] = hist_obs[i][0, :]

        torch_policy_input = torch.tensor(policy_input)
        torch_policy_action = policy_model(torch_policy_input)[0].detach().numpy()
        torch_policy_action = numpy.clip(torch_policy_action, -XBotLCfg.normalization.clip_actions,
                                         XBotLCfg.normalization.clip_actions)

        # 记录上一次的 action
        policy_action = torch_policy_action

        target_q = policy_action * XBotLCfg.control.action_scale
    else:
        target_q = policy_action * XBotLCfg.control.action_scale if policy_action is not None else numpy.zeros(
            policy_control_num_of_joints)

    target_dq = numpy.zeros((policy_control_num_of_joints), dtype=numpy.double)
    # Generate PD control
    tau = pd_control(target_q, numpy.radians(joint_measured_position), XBotLCfg.robot_config.kps,
                     target_dq, numpy.radians(joint_measured_velocity), XBotLCfg.robot_config.kds)  # Calc torques
    tau = numpy.clip(tau, -XBotLCfg.robot_config.tau_limit, XBotLCfg.robot_config.tau_limit)  # Clamp torques

    # 控制参数如不需修改，则只需要发送一次即可
    joint_target_control_mode = numpy.array([
        # left leg
        fourier_grx.JointControlMode.PD, fourier_grx.JointControlMode.PD, fourier_grx.JointControlMode.PD,
        fourier_grx.JointControlMode.PD, fourier_grx.JointControlMode.PD, fourier_grx.JointControlMode.PD,
        # right leg
        fourier_grx.JointControlMode.PD, fourier_grx.JointControlMode.PD, fourier_grx.JointControlMode.PD,
        fourier_grx.JointControlMode.PD, fourier_grx.JointControlMode.PD, fourier_grx.JointControlMode.PD,
    ])
    joint_target_kp = XBotLCfg.robot_config.kps
    joint_target_kd = XBotLCfg.robot_config.kds
    joint_target_position = numpy.zeros(robot_num_of_joints)

    joint_target_position[-policy_control_num_of_joints:] = numpy.degrees(target_q)

    # --------------------------------------------------

    # set control
    """
    control:
    - control_mode
    - pd_control_kp
    - pd_control_kd
    - position: degree
    """
    control_dict = {
        "control_mode": joint_target_control_mode,
        "pd_control_kp": joint_target_kp,
        "pd_control_kd": joint_target_kd,
        "position": joint_target_position,
    }

    # output control
    control_system.robot_control_loop_set_control(control_dict=control_dict)
    count_lowlevel += 1


def pd_control(target_q, q, kp, target_dq, dq, kd):
    '''Calculates torques from position commands
    '''
    return (target_q - q) * kp + (target_dq - dq) * kd


if __name__ == "__main__":
    main()
