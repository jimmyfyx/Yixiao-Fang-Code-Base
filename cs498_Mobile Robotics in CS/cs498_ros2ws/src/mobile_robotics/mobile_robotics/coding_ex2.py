# Student name: 

import math
import numpy as np
from numpy import linalg as LA
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TransformStamped, Accel
from tf2_ros import TransformBroadcaster

from std_msgs.msg import String, Float32
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
import matplotlib.pyplot as plt
import time
from mobile_robotics.utils import quaternion_from_euler, lonlat2xyz, quat2euler


class ExtendedKalmanFilter(Node):

    
    def __init__(self):
        super().__init__('ExtendedKalmanFilter')
        
        
        #array to save the sensor measurements from the rosbag file
        #measure = [p, q, r, fx, fy, fz, x, y, z, vx, vy, vz] 
        self.measure = np.zeros(12)
        
        #Initialization of the variables used to generate the plots.
        self.PHI = []  
        self.PSI = []
        self.THETA = []
        self.P_R = []
        self.P_R1 = []
        self.P_R2 = []
        self.Pos = []
        self.Vel = []
        self.Quater = []
        self.measure_PosX = []
        self.measure_PosY = []
        self.measure_PosZ = []
        self.P_angular = []
        self.Q_angular = []
        self.R_angular = []
        self.P_raw_angular = []
        self.Q_raw_angular = []
        self.R_raw_angular = []
        self.Bias =[]
        
        self.POS_X = []
        self.POS_Y = []
        
        
        #Initialization of the variables used in the EKF
        
        # initial bias values, these are gyroscope and accelerometer biases
        self.bp= 0.0
        self.bq= 0.0
        self.br= 0.0
        self.bfx = 0.0
        self.bfy = 0.0
        self.bfz = 0.0
        # initial rotation
        self.q2, self.q3, self.q4, self.q1 = quaternion_from_euler(0.0, 0.0, np.pi/2) #[qx,qy,qz,qw]

        #initialize the state vector [x y z vx vy vz          quat    gyro-bias accl-bias]
        self.xhat = np.array([[0, 0, 0, 0, 0, 0, self.q1, self.q2, self.q3, self.q4, self.bp, self.bq, self.br, self.bfx, self.bfy, self.bfz]]).T

        self.rgps=np.array([-0.15, 0 ,0]) #This is the location of the GPS wrt CG, this is very important
        
        #noise params process noise (my gift to you :))
        self.Q = np.diag([0.1, 0.1, 0.1, 0.01, 0.01, 0.01, 0.5, 0.5, 0.5, 0.5, 0.01, 0.01, 0.01, 0.001, 0.001, 0.001]) 
        #measurement noise
        #GPS position and velocity
        self.R = np.diag([10, 10, 10, 2, 2, 2]) 
        
       
        #Initialize P, the covariance matrix
        self.P = np.diag([30, 30, 30, 3, 3, 3, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1])
        self.Pdot=self.P*0.0
        
        self.time = []
        self.loop_t = 0

        # You might find these blocks useful when assembling the transition matrices
        self.Z = np.zeros((3,3))
        self.I = np.eye(3,3)
        self.Z34 = np.zeros((3,4))
        self.Z43 = np.zeros((4,3))
        self.Z36 = np.zeros((3,6))

        self.lat = 0
        self.lon = 0
        self.lat0 = 0
        self.lon0 = 0
        self.flag_lat = False
        self.flag_lon = False
        self.dt = 0.0125 #set sample time

        # Ros subscribers and publishers
        self.subscription_imu = self.create_subscription(Imu, 'terrasentia/imu', self.callback_imu, 10)
        self.subscription_gps_lat = self.create_subscription(Float32, 'gps_latitude', self.callback_gps_lat, 10)
        self.subscription_gps_lon = self.create_subscription(Float32, 'gps_longitude', self.callback_gps_lon, 10)
        self.subscription_gps_speed_north = self.create_subscription(Float32, 'gps_speed_north', self.callback_gps_speed_north, 10)
        self.subscription_gps_speend_east = self.create_subscription(Float32, 'gps_speed_east', self.callback_gps_speed_east, 10)
        
        self.timer_ekf = self.create_timer(self.dt, self.ekf_callback)
        self.timer_plot = self.create_timer(5, self.plot_data_callback)

        # odometry publisher
        self.odom_pub = self.create_publisher(Odometry, 'odom', 10)
        self.timer = self.create_timer(0.1, self.odom_callback)

    def odom_callback(self):
        frame_id = 'odom'
        
        odom = Odometry()
        odom.header.frame_id = frame_id
        odom.pose.pose.position.x = self.xhat[0, 0]
        odom.pose.pose.position.y = self.xhat[1, 0]
        odom.pose.pose.position.z = self.xhat[2, 0]
        odom.pose.pose.orientation.x = self.xhat[6, 0]
        odom.pose.pose.orientation.y = self.xhat[7, 0]
        odom.pose.pose.orientation.z = self.xhat[8, 0]
        odom.pose.pose.orientation.w = self.xhat[9, 0]
        odom.twist.twist.linear.x = self.xhat[3, 0]
        odom.twist.twist.linear.y = self.xhat[4, 0]
        odom.twist.twist.linear.z = self.xhat[5, 0]

        odom.twist.twist.angular.x = 0.0
        odom.twist.twist.angular.y = 0.0
        odom.twist.twist.angular.z = self.measure[2]-self.xhat[12,0]

        self.odom_pub.publish(odom)

    
    def callback_imu(self,msg):
        #measurement vector = [p, q, r, fx, fy, fz, x, y, z, vx, vy, vz]
        # In practice, the IMU measurements should be filtered. In this coding exercise, we are just going to clip
        # the values of velocity and acceleration to keep them in physically possible intervals.
        self.measure[0] = np.clip(msg.angular_velocity.x,-5,5) #(-5,5)
        self.measure[1] = np.clip(msg.angular_velocity.y,-5,5) #..(-5,5)
        self.measure[2] = np.clip(msg.angular_velocity.z,-5,5) #..(-5,5)
        self.measure[3] = np.clip(msg.linear_acceleration.x,-6,6) #..(-6,6)
        self.measure[4] = np.clip(msg.linear_acceleration.y,-6,6) #..(-6,6)
        self.measure[5] = np.clip(msg.linear_acceleration.z,-16,-4) #..(-16,-4) 
 
    def callback_gps_lat(self, msg):
        self.lat = msg.data
        if (self.flag_lat == False): #just a trick to recover the initial value of latitude
            self.lat0 = msg.data
            self.flag_lat = True
        
        if (self.flag_lat and self.flag_lon): 
            x, y = lonlat2xyz(self.lat, self.lon, self.lat0, self.lon0) # convert latitude and longitude to x and y coordinates
            self.measure[6] = x
            self.measure[7] = y
            self.measure[8] = 0.0 

    
    def callback_gps_lon(self, msg):
        self.lon = msg.data
        if (self.flag_lon == False): #just a trick to recover the initial value of longitude
            self.lon0 = msg.data
            self.flag_lon = True    
    
    def callback_gps_speed_east(self, msg): 
        self.measure[9] = msg.data # ..
        self.measure[11] = 0.0 # vz

    def callback_gps_speed_north(self, msg):
        self.measure[10] = msg.data # vy

   
    def ekf_callback(self):
        #print("iteration:  ",self.loop_t)
        if (self.flag_lat and self.flag_lon):  #Trick  to sincronize rosbag with EKF
            self.ekf_function()
        else:
            print("Play the rosbag file...")

    
    
    def ekf_function(self):
        
        # Adjusting angular velocities and acceleration with the corresponding bias
        self.p = (self.measure[0]-self.xhat[10,0])
        self.q = (self.measure[1]-self.xhat[11,0])
        self.r = self.measure[2]-self.xhat[12,0]
        self.fx = (self.measure[3]-self.xhat[13,0])
        self.fy = (self.measure[4]-self.xhat[14,0])
        self.fz = -self.measure[5]-self.xhat[15,0]
        
        # Get the current quaternion values from the state vector
        # Remember again the state vector [x y z vx vy vz q1 q2 q3 q4 bp bq br bx by bz]
        self.quat = np.array([[self.xhat[6,0], self.xhat[7,0], self.xhat[8,0], self.xhat[9,0]]]).T
    
        self.q1 = self.quat[0,0]
        self.q2 = self.quat[1,0]
        self.q3 = self.quat[2,0]
        self.q4 = self.quat[3,0]
                
        # Rotation matrix: body to inertial frame
        self.R_bi = np.array([[pow(self.q1,2)+pow(self.q2,2)-pow(self.q3,2)-pow(self.q4,2), 2*(self.q2*self.q3-self.q1*self.q4), 2*(self.q2*self.q4+self.q1*self.q3)],
                          [2*(self.q2*self.q3+self.q1*self.q4), pow(self.q1,2)-pow(self.q2,2)+pow(self.q3,2)-pow(self.q4,2), 2*(self.q3*self.q4-self.q1*self.q2)],
                          [2*(self.q2*self.q4-self.q1*self.q3), 2*(self.q3*self.q4+self.q1*self.q2), pow(self.q1,2)-pow(self.q2,2)-pow(self.q3,2)+pow(self.q4,2)]])
        
        """
        Prediction step
        """
        '''
        First write out all the dots for all the states, e.g. pxdot, pydot, q1dot etc
        '''
        # position dot
        # pdot_vec = np.matmul(self.R_bi, np.array([self.xhat[3,0], self.xhat[4,0], self.xhat[5,0]]).T)
        pxdot = self.xhat[3, 0]
        pydot = self.xhat[4, 0]
        pzdot = self.xhat[5, 0]

        # velocity dot (acceleration)
        vdot_vec = np.matmul(self.R_bi, np.array([self.fx, self.fy, self.fz]).T)
        vxdot = vdot_vec[0]
        vydot = vdot_vec[1]
        vzdot = vdot_vec[2]

        # quaternion dot
        omega_mat = np.array([[0, self.p, self.q, self.r], [-self.p, 0, -self.r, self.q], [-self.q, self.r, 0, -self.p], [-self.r, -self.q, self.p, 0]])
        qdot_vec = np.matmul(omega_mat, self.quat) * -0.5
        q1dot = qdot_vec[0]
        q2dot = qdot_vec[1]
        q3dot = qdot_vec[2]
        q4dot = qdot_vec[3]

        '''
        Now integrate Euler Integration for Process Updates and Covariance Updates
        '''
        # Euler works fine
        # Remember again the state vector [x y z vx vy vz q1 q2 q3 q4 bp bq br bx by bz]
        self.xhat[0,0] = self.xhat[0,0] + self.dt * pxdot
        self.xhat[1,0] = self.xhat[1,0] + self.dt * pydot
        self.xhat[2,0] = self.xhat[2,0] + self.dt * pzdot 
        self.xhat[3,0] = self.xhat[3,0] + self.dt * vxdot  
        self.xhat[4,0] = self.xhat[4,0] + self.dt * vydot
        self.xhat[5,0] = self.xhat[5,0] + self.dt * (vzdot - 9.801) # .. Do not forget Gravity (9.801 m/s2) 
        self.xhat[6,0] = self.xhat[6,0] + self.dt * q1dot
        self.xhat[7,0] = self.xhat[7,0] + self.dt * q2dot 
        self.xhat[8,0] = self.xhat[8,0] + self.dt * q3dot 
        self.xhat[9,0] = self.xhat[9,0] + self.dt * q4dot

        print("x ekf: ", self.xhat[0,0])
        print("y ekf: ", self.xhat[1,0])
        print("z ekf: ", self.xhat[2,0])
        
        # Extract and normalize the quat    
        self.quat = np.array([[self.xhat[6,0], self.xhat[7,0], self.xhat[8,0], self.xhat[9,0]]]).T
        # .. Normailize quat
        self.quat = self.quat / np.linalg.norm(self.quat)
        
        #re-assign quat
        self.xhat[6,0] = self.quat[0,0]
        self.xhat[7,0] = self.quat[1,0]
        self.xhat[8,0] = self.quat[2,0]
        self.xhat[9,0] = self.quat[3,0]
        
        '''        
        Now write out all the partials to compute the transition matrix Phi
        '''
        q1 = self.quat[0,0]
        q2 = self.quat[1,0]
        q3 = self.quat[2,0]
        q4 = self.quat[3,0]
        # vdot_vec = np.matmul(self.R_bi, np.array([self.fx, self.fy, self.fz]).T)
        ax = self.fx
        ay = self.fy
        az = self.fz
        #delV/delQ
        Fvq = np.array([[2 * (q1 * ax - q4 * ay + q3 * az), 2 * (q2 * ax + q3 * ay + q4 * az), 2 * (-q3 * ax + q2 * ay + q1 * az), 2 * (-q4 * ax - q1 * ay + q2 * az)],
                        [2 * (q4 * ax + q1 * ay - q2 * az), 2 * (q3 * ax - q2 * ay - q1 * az), 2 * (q2 * ax + q3 * ay + q4 * az), 2 * (q1 * ax - q4 * ay + q3 * az)],
                        [2 * (-q3 * ax + q2 * ay + q1 * az), 2 * (q4 * ax + q1 * ay - q2 * az), 2 * (-q1 * ax + q4 * ay - q3 * az), 2 * (q2 * ax + q3 * ay + q4 * az)]])

        #delV/del_abias
        Fvb = -self.R_bi
        
        #delQ/delQ
        Fqq = -0.5 * omega_mat
     
        #delQ/del_gyrobias
        Fqb = 0.5 * np.array([[q2, q3, q4],
                              [-q1, q4, -q3],
                              [-q4, -q1, q2],
                              [q3, -q2, -q1]])

        '''
        Now assemble the Transition matrix A
        '''
        first_row = np.concatenate((np.concatenate((np.concatenate((np.concatenate((self.Z, self.I), axis = 1), self.Z34), axis = 1), self.Z), axis = 1), self.Z), axis = 1)
        second_row = np.concatenate((np.concatenate((np.concatenate((np.concatenate((self.Z, self.Z), axis = 1), Fvq), axis = 1), self.Z), axis = 1), Fvb), axis = 1)
        third_row = np.concatenate((np.concatenate((np.concatenate((np.concatenate((self.Z43, self.Z43), axis = 1), Fqq), axis = 1), Fqb), axis = 1), self.Z43), axis = 1)
        fourth_row = np.concatenate((np.concatenate((np.concatenate((np.concatenate((self.Z, self.Z), axis = 1), self.Z34), axis = 1), self.Z), axis = 1), self.Z), axis = 1)
        fifth_row = np.concatenate((np.concatenate((np.concatenate((np.concatenate((self.Z, self.Z), axis = 1), self.Z34), axis = 1), self.Z), axis = 1), self.Z), axis = 1)
        A = np.concatenate((np.concatenate((np.concatenate((np.concatenate((first_row, second_row), axis = 0), third_row), axis = 0), fourth_row), axis = 0), fifth_row), axis = 0)

        
        '''
        Propagate the error covariance matrix, I suggest using the continuous integration since Q, R are not discretized
        ''' 
        #Pdot = A@P+P@A.transpose() + Q
        #P = P +Pdot*dt
        Pdot = np.matmul(A, self.P) + np.matmul(self.P, A.T) + self.Q 
        self.P = self.P + Pdot * self.dt  
        
        
        """
        Correction step
        """
        #Get measurements 3 positions and 3 velocities from GPS
        self.z = np.array([[self.measure[6], self.measure[7], self.measure[8], self.measure[9], self.measure[10], self.measure[11]]]).T #x y z vx vy vz
    
        # Write out the measurement matrix linearization to get H
        r = self.rgps[0]
        # del v/del q
        
        Hvq = np.array([[2 * r * q3 * self.q + 2 * r * q4 * self.r, 2 * r * q4 * self.q - 2 * r * q3 * self.r, 2 * r * q1 * self.q - 2 * r * q2 * self.r, 2 * r * q2 * self.q + 2 * r * q1 * self.r],
                        [-2 * r * q2 * self.q - 2 * r * q1 * self.r, 2 * r * q2 * self.r - 2 * r * q1 * self.q, 2 * r * q4 * self.q - 2 * r * q3 * self.r, 2 * r * q3 * self.q + 2 * r * q4 * self.r],
                        [2 * r * q1 * self.q - 2 * r * q2 * self.r,  -2 * r * q2 * self.q - 2 * r * q1 * self.r, -2 * r * q3 * self.q - 2 * r * q4 * self.r, 2 * r * q4 * self.q - 2 * r * q3 * self.r]])  
        
        # del P/del q
        Hxq = np.array([[-2 * r * q1, -2 * r * q2, 2 * r * q3, 2 * r * q4],
                        [-2 * r * q4, -2 * r * q3, -2 * r * q2, -2 * r * q1],
                        [2 * r * q3,  -2 * r * q4, 2 * r * q1, -2 * r * q2]]) 
        
        # Assemble H
        first_row = np.concatenate((np.concatenate((np.concatenate((self.I, self.Z), axis = 1), Hxq), axis = 1), self.Z36), axis = 1)
        second_row = np.concatenate((np.concatenate((np.concatenate((self.Z, self.I), axis = 1), Hvq), axis = 1), self.Z36), axis = 1)
        H = np.concatenate((first_row, second_row), axis = 0)

        #Compute Kalman gain
        P_Ht = np.matmul(self.P, H.T)
        HPHt = np.matmul(np.matmul(H, self.P), H.T)
        L = np.matmul(P_Ht, np.linalg.inv(HPHt + self.R))# Kalman gain
        
        #Perform xhat correction    xhat = xhat + L@(z-H@xhat)
        Hx = np.matmul(H, self.xhat)
        self.xhat = self.xhat + np.matmul(L, self.z - Hx)
        
        #propagate error covariance approximation P = (np.eye(16,16)-L@H)@P
        # S = np.matmul(np.matmul(H, self.P), H.T) + self.R
        # LSLt = np.matmul(np.matmul(L, S), L.T)
        L_H = np.matmul(L, H)
        self.P = np.matmul(np.eye(16, 16) - L_H, self.P) 

        #Now let us do some book-keeping 
        # Get some Euler angles
        
        phi, theta, psi = quat2euler(self.quat.T)

        self.PHI.append(phi*180/math.pi)
        self.THETA.append(theta*180/math.pi)
        self.PSI.append(psi*180/math.pi)
    
          
        # Saving data for the plots. Uncomment the 4 lines below once you have finished the ekf function

        DP = np.diag(self.P)
        self.P_R.append(DP[0:3])
        self.P_R1.append(DP[3:6])
        self.P_R2.append(DP[6:10])
        self.Pos.append(self.xhat[0:3].T[0])
        self.POS_X.append(self.xhat[0,0])
        self.POS_Y.append(self.xhat[1,0])
        self.Vel.append(self.xhat[3:6].T[0])
        self.Quater.append(self.xhat[6:10].T[0])
        self.Bias.append(self.xhat[10:16].T[0])
        B = self.measure[6:9].T
        self.measure_PosX.append(B[0])
        self.measure_PosY.append(B[1])
        self.measure_PosZ.append(B[2])

        self.P_angular.append(self.p)
        self.Q_angular.append(self.q)
        self.R_angular.append(self.r)

        self.loop_t += 1
        self.time.append(self.loop_t*self.dt)

    def plot_data_callback(self):

        # plt.figure(1)
        # plt.clf()
        # plt.plot(self.time,self.PHI,'b', self.time, self.THETA, 'g', self.time,self.PSI, 'r')
        # plt.legend(['phi','theta','psi'])
        # plt.title('Phi, Theta, Psi [deg]')

        # plt.figure(2)
        # plt.clf()
        # plt.plot(self.measure_PosX, self.measure_PosY, self.POS_X, self.POS_Y)
        # plt.title('xy trajectory')
        # plt.legend(['GPS','EKF'])

        # plt.figure(3)
        # plt.clf()
        # plt.plot(self.time,self.P_R)
        # plt.title('Covariance of Position')
        # plt.legend(['px','py','pz'])
        # plt.figure(4)
        # plt.clf()
        # plt.plot(self.time,self.P_R1)
        # plt.legend(['pxdot','pydot','pzdot'])
        # plt.title('Covariance of Velocities')
        # plt.figure(5)
        # plt.clf()
        # plt.plot(self.time,self.P_R2)
        # plt.title('Covariance of Quaternions')
        # plt.figure(6)
        # plt.clf()
        # plt.plot(self.time,self.Pos,self.time,self.measure_PosX,'r:', self.time,self.measure_PosY,'r:', self.time,self.measure_PosZ,'r:')
        # plt.legend(['X_ekf', 'Y_ekf', 'Z_ekf','Xgps','Ygps','Z_0'])
        # plt.title('Position')
        # plt.figure(7)
        # plt.clf()
        # plt.plot(self.time,self.Vel)
        # plt.title('vel x y z')
        # plt.figure(8)
        # plt.clf()
        # plt.plot(self.time,self.Quater)
        # plt.title('Quat')
        # plt.figure(9)
        # plt.clf()
        # plt.plot(self.time,self.P_angular,self.time,self.Q_angular,self.time,self.R_angular)
        # plt.title('OMEGA with Bias')
        # plt.legend(['p','q','r'])

        # plt.figure(10)
        # plt.clf()
        # plt.plot(self.time,self.Bias)
        # plt.title('Gyroscope and accelerometer Bias')
        # plt.legend(['bp','bq','br','bfx','bfy','bfz'])
                
        plt.ion()
        plt.show()
        plt.pause(0.0001)
        

def main(args=None):
    rclpy.init(args=args)

    ekf_node = ExtendedKalmanFilter()
    
    rclpy.spin(ekf_node)

   
    ekf_node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
