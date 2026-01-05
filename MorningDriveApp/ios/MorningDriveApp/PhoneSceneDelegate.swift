import UIKit
import React
import React_RCTAppDelegate
import ReactAppDependencyProvider

class PhoneSceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        print("[PhoneSceneDelegate] scene willConnectTo called")
        guard let windowScene = scene as? UIWindowScene else {
            print("[PhoneSceneDelegate] ERROR: scene is not UIWindowScene")
            return
        }

        guard let appDelegate = UIApplication.shared.delegate as? AppDelegate else {
            print("[PhoneSceneDelegate] ERROR: Could not get AppDelegate")
            return
        }

        guard let factory = appDelegate.reactNativeFactory else {
            print("[PhoneSceneDelegate] ERROR: reactNativeFactory is nil")
            return
        }

        print("[PhoneSceneDelegate] Creating window...")
        window = UIWindow(windowScene: windowScene)

        print("[PhoneSceneDelegate] Starting React Native...")
        factory.startReactNative(
            withModuleName: "MorningDriveApp",
            in: window,
            launchOptions: nil
        )

        window?.makeKeyAndVisible()
        print("[PhoneSceneDelegate] Window made key and visible")
    }
}
