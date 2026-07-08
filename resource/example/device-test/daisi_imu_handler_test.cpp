#include "protocal.hpp"
#ifdef DSIMU
#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <glog/logging.h>
#include <string>
#include <thread>
#include <unistd.h>
#include "entity/device/imu_handler.hpp"
#include "Math/rot.hpp"

namespace {

constexpr auto kSamplePeriod = std::chrono::microseconds(5000);  // 200 Hz

struct ImuSample {
    float quat[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    float omega[3] = {0.0f, 0.0f, 0.0f};
    float acc[3] = {0.0f, 0.0f, 0.0f};
    EulerAngles rpy{};
    std::array<double, 3> projected_gravity = {0.0, 0.0, -1.0};
};

ImuSample readSample(IMUHandler& handler) {
    ImuSample sample;
    handler.readQuatOmegaAcc(sample.quat, sample.omega, sample.acc);

    Quaternion q;
    q.w = sample.quat[0];
    q.x = sample.quat[1];
    q.y = sample.quat[2];
    q.z = sample.quat[3];
    sample.rpy = quaternionToEulerAngles(q);

    const std::array<double, 3> gravity_vect = {0.0, 0.0, -1.0};
    sample.projected_gravity = rotate_vector(q.normalized(), gravity_vect);
    return sample;
}

double wrapPi(double x) {
    while (x > M_PI) x -= 2.0 * M_PI;
    while (x < -M_PI) x += 2.0 * M_PI;
    return x;
}

std::array<double, 3> rpyDiff(const ImuSample& a, const ImuSample& b) {
    return {
        wrapPi(a.rpy.roll - b.rpy.roll),
        wrapPi(a.rpy.pitch - b.rpy.pitch),
        wrapPi(a.rpy.yaw - b.rpy.yaw),
    };
}

std::array<double, 3> vecDiff(const float* a, const float* b) {
    return {a[0] - b[0], a[1] - b[1], a[2] - b[2]};
}

void logVec(const char* name, const std::array<double, 3>& v) {
    LOG(INFO) << name << ": " << v[0] << " " << v[1] << " " << v[2];
}

void logFloatVec(const char* name, const float* v) {
    LOG(INFO) << name << ": " << v[0] << " " << v[1] << " " << v[2];
}

}  // namespace

int main(int argc, char** argv) {
    google::InitGoogleLogging(argv[0]);
    FLAGS_logtostderr = 1;

    const std::string imu_a_dev = argc > 1 ? argv[1] : "/dev/ttyUSB_imu";
    const std::string imu_b_dev = argc > 2 ? argv[2] : "/dev/ttyUSB_imu2";

    LOG(INFO) << "IMU A: " << imu_a_dev;
    LOG(INFO) << "IMU B: " << imu_b_dev;

    IMUHandler imu_a;
    IMUHandler imu_b;
    imu_a.init(imu_a_dev);
    imu_b.init(imu_b_dev);
    imu_a.start();
    imu_b.start();

    usleep(500000);
    const ImuSample init_a = readSample(imu_a);
    const ImuSample init_b = readSample(imu_b);
    const std::array<double, 3> initial_rpy_delta = rpyDiff(init_a, init_b);

    LOG(INFO) << "Initial relative rpy delta A-B captured.";
    logVec("initial_rpy_delta", initial_rpy_delta);

    int cur_iter = 0;
    auto next_sample_time = std::chrono::steady_clock::now();
    while (true) {
        next_sample_time += kSamplePeriod;
        const ImuSample a = readSample(imu_a);
        const ImuSample b = readSample(imu_b);
        const auto rpy_delta = rpyDiff(a, b);
        const std::array<double, 3> rpy_drift = {
            wrapPi(rpy_delta[0] - initial_rpy_delta[0]),
            wrapPi(rpy_delta[1] - initial_rpy_delta[1]),
            wrapPi(rpy_delta[2] - initial_rpy_delta[2]),
        };

        LOG(INFO) << "cur_iter: " << cur_iter++;
        LOG(INFO) << "imu_a rpy: " << a.rpy.roll << " " << a.rpy.pitch << " " << a.rpy.yaw;
        LOG(INFO) << "imu_b rpy: " << b.rpy.roll << " " << b.rpy.pitch << " " << b.rpy.yaw;
        logVec("rpy_delta_a_minus_b", rpy_delta);
        logVec("relative_rpy_drift_from_start", rpy_drift);
        logVec("omega_delta_a_minus_b", vecDiff(a.omega, b.omega));
        logVec("acc_delta_a_minus_b", vecDiff(a.acc, b.acc));
        logFloatVec("imu_a_omega", a.omega);
        logFloatVec("imu_b_omega", b.omega);
        logFloatVec("imu_a_acc", a.acc);
        logFloatVec("imu_b_acc", b.acc);
        std::this_thread::sleep_until(next_sample_time);
    }

    return 0;
}
#else
#include <glog/logging.h>
int main(int argc, char** argv) {
    google::InitGoogleLogging(argv[0]);
    FLAGS_logtostderr = 1;
    LOG(INFO) << "DSIMU is not defined";
    return 0;
}
#endif
