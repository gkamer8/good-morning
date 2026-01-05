import UIKit
import React
import React_RCTAppDelegate
import ReactAppDependencyProvider
import CarPlay

@main
class AppDelegate: UIResponder, UIApplicationDelegate {
  var window: UIWindow?

  var reactNativeDelegate: ReactNativeDelegate?
  var reactNativeFactory: RCTReactNativeFactory?

  func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
  ) -> Bool {
    print("[AppDelegate] didFinishLaunchingWithOptions")
    // Initialize React Native factory but DON'T create window or start RN here
    // The PhoneSceneDelegate will handle that for phone scenes
    let delegate = ReactNativeDelegate()
    let factory = RCTReactNativeFactory(delegate: delegate)
    delegate.dependencyProvider = RCTAppDependencyProvider()

    reactNativeDelegate = delegate
    reactNativeFactory = factory

    return true
  }

  // MARK: - Scene Configuration
  func application(
    _ application: UIApplication,
    configurationForConnecting connectingSceneSession: UISceneSession,
    options: UIScene.ConnectionOptions
  ) -> UISceneConfiguration {
    print("[AppDelegate] configurationForConnecting role: \(connectingSceneSession.role.rawValue)")

    if connectingSceneSession.role == UISceneSession.Role.carTemplateApplication {
      print("[AppDelegate] Creating CarPlay scene configuration")
      let config = UISceneConfiguration(name: "CarPlay", sessionRole: connectingSceneSession.role)
      config.delegateClass = NSClassFromString("CarSceneDelegate") as? UIResponder.Type
      return config
    }

    print("[AppDelegate] Creating Phone scene configuration")
    let config = UISceneConfiguration(name: "Phone", sessionRole: connectingSceneSession.role)
    config.delegateClass = PhoneSceneDelegate.self
    return config
  }
}

class ReactNativeDelegate: RCTDefaultReactNativeFactoryDelegate {
  override func sourceURL(for bridge: RCTBridge) -> URL? {
    self.bundleURL()
  }

  override func bundleURL() -> URL? {
#if DEBUG
    RCTBundleURLProvider.sharedSettings().jsBundleURL(forBundleRoot: "index")
#else
    Bundle.main.url(forResource: "main", withExtension: "jsbundle")
#endif
  }
}
