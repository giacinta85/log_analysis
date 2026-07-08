#include "protocal.hpp"
#ifdef DSIMU
#include <array>
#include <chrono>
#include <glog/logging.h>
#include <string>
#include <thread>
#include <unistd.h>
#include "Math/rot.hpp"
#include "entity/device/imu_handler.hpp"

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

void logFloatVec(const char* name, const float* v) {
    LOG(INFO) << name << ": " << v[0] << " " << v[1] << " " << v[2];
}

void logVec(const char* name, const std::array<double, 3>& v) {
    LOG(INFO) << name << ": " << v[0] << " " << v[1] << " " << v[2];
}

}  // namespace

int main(int argc, char** argv) {
    google::InitGoogleLogging(argv[0]);
    FLAGS_logtostderr = 1;

    const std::string imu_dev = argc > 1 ? argv[1] : "/dev/ttyUSB0";
    LOG(INFO) << "IMU: " << imu_dev;

    IMUHandler handler;
    handler.init(imu_dev);
    handler.start();

    int cur_iter = 0;
    auto next_sample_time = std::chrono::steady_clock::now();
    while (true) {
        next_sample_time += kSamplePeriod;
        const ImuSample sample = readSample(handler);

        LOG(INFO) << "cur_iter: " << cur_iter++;
        LOG(INFO) << "rpy: " << sample.rpy.roll << " " << sample.rpy.pitch << " " << sample.rpy.yaw;
        LOG(INFO) << "quat: " << sample.quat[0] << " " << sample.quat[1] << " " << sample.quat[2] << " " << sample.quat[3];
        logFloatVec("omega", sample.omega);
        logFloatVec("acc", sample.acc);
        logVec("projected_gravity", sample.projected_gravity);
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
