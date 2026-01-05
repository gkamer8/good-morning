#import "CarSceneDelegate.h"
#import <RNCarPlay.h>
#import "RNCPStore.h"

@interface CarSceneDelegate ()
@property (nonatomic, strong) CPInterfaceController *storedInterfaceController;
@property (nonatomic, strong) CPWindow *storedWindow;
@property (nonatomic, strong) NSTimer *retryTimer;
@property (nonatomic, assign) int retryCount;
@end

@implementation CarSceneDelegate

- (instancetype)init {
    self = [super init];
    if (self) {
        NSLog(@"[CarPlay Native] CarSceneDelegate initialized!");
        _retryCount = 0;
    }
    return self;
}

- (void)templateApplicationScene:(CPTemplateApplicationScene *)templateApplicationScene
   didConnectInterfaceController:(CPInterfaceController *)interfaceController {
    NSLog(@"[CarPlay Native] ========================================");
    NSLog(@"[CarPlay Native] CarPlay CONNECTED!");
    NSLog(@"[CarPlay Native] interfaceController=%@", interfaceController);
    NSLog(@"[CarPlay Native] carWindow=%@", templateApplicationScene.carWindow);
    NSLog(@"[CarPlay Native] ========================================");

    // Store for later retry if needed
    self.storedInterfaceController = interfaceController;
    self.storedWindow = templateApplicationScene.carWindow;
    self.retryCount = 0;

    // Connect to RNCarPlay - this sends the event to JS
    [RNCarPlay connectWithInterfaceController:interfaceController window:templateApplicationScene.carWindow];
    NSLog(@"[CarPlay Native] Called RNCarPlay connectWithInterfaceController");

    // TEMPORARY: Set a fallback template directly from native to prove CarPlay works
    // This bypasses JS until we fix the event emission issue
    // Give JS 6 seconds to set up templates before showing fallback
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(6.0 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        RNCPStore *store = [RNCPStore sharedManager];
        if (store.interfaceController.rootTemplate == nil) {
            NSLog(@"[CarPlay Native] No root template set by JS after 6s, setting fallback template");

            CPListItem *item1 = [[CPListItem alloc] initWithText:@"Morning Drive" detailText:@"Tap to play your briefing"];
            CPListItem *item2 = [[CPListItem alloc] initWithText:@"Waiting for JS..." detailText:@"Event bridge issue"];

            CPListSection *section = [[CPListSection alloc] initWithItems:@[item1, item2] header:@"Briefings" sectionIndexTitle:nil];
            CPListTemplate *listTemplate = [[CPListTemplate alloc] initWithTitle:@"Morning Drive" sections:@[section]];

            [interfaceController setRootTemplate:listTemplate animated:YES completion:^(BOOL done, NSError * _Nullable err) {
                if (err) {
                    NSLog(@"[CarPlay Native] Error setting fallback template: %@", err);
                } else {
                    NSLog(@"[CarPlay Native] Fallback template set successfully!");
                }
            }];
        } else {
            NSLog(@"[CarPlay Native] JS already set a root template, good!");
        }
    });

    // Start retry timer to keep trying to notify JS
    [self startRetryTimer];
}

- (void)startRetryTimer {
    [self.retryTimer invalidate];
    self.retryTimer = [NSTimer scheduledTimerWithTimeInterval:0.5
                                                       target:self
                                                     selector:@selector(retryConnection)
                                                     userInfo:nil
                                                      repeats:YES];
}

- (void)retryConnection {
    self.retryCount++;
    NSLog(@"[CarPlay Native] Retry connection attempt #%d", self.retryCount);

    if (self.storedInterfaceController && self.storedWindow) {
        // Re-call connect to try sending the event again
        [RNCarPlay connectWithInterfaceController:self.storedInterfaceController window:self.storedWindow];
    }

    // Stop after 20 attempts (10 seconds)
    if (self.retryCount >= 20) {
        NSLog(@"[CarPlay Native] Stopping retry timer after %d attempts", self.retryCount);
        [self.retryTimer invalidate];
        self.retryTimer = nil;
    }
}

- (void)templateApplicationScene:(CPTemplateApplicationScene *)templateApplicationScene
   didDisconnectInterfaceController:(CPInterfaceController *)interfaceController {
    NSLog(@"[CarPlay Native] CarPlay DISCONNECTED!");
    [self.retryTimer invalidate];
    self.retryTimer = nil;
    self.storedInterfaceController = nil;
    self.storedWindow = nil;
    [RNCarPlay disconnect];
}

- (void)sceneWillEnterForeground:(UIScene *)scene {
    NSLog(@"[CarPlay Native] Scene will enter foreground: %@", scene);
}

- (void)sceneDidBecomeActive:(UIScene *)scene {
    NSLog(@"[CarPlay Native] Scene did become active: %@", scene);
}

@end
